"""方向三：受控执行层骨架（模拟环境版）。

设计对应文档要求：
- 战略层：任务/步骤依赖（Plan/Step）
- 战术层：路径规划与局部重规划（A* 网格）
- 执行层：短动作 + 反馈判断（Environment.execute / observe）
- 安全监督：重试上限、高风险确认、人工停止、暂停（SafetySupervisor）
- 错误分级：L1 局部调整 / L2 本步重规划 / L3 流程重规划 / L4 安全暂停
- 检查点：恢复时重新观察环境，不依赖历史状态

注意：本模块只在自建模拟环境中运行，不连接真实游戏。
"""
from __future__ import annotations

import heapq
import json
import random
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Step:
    id: str
    goal: str
    action: str  # "move" | "interact"
    expected: str
    timeout_s: float = 5.0
    max_retries: int = 3
    risk: Risk = Risk.LOW
    requires_confirmation: bool = False
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    first_try_ok: bool = False
    target: tuple[int, int] | None = None


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    index: int = 0

    def current(self) -> Step | None:
        return self.steps[self.index] if self.index < len(self.steps) else None

    def advance(self) -> None:
        if self.current():
            self.current().status = StepStatus.DONE
        self.index += 1


@dataclass
class Faults:
    drift_prob: float = 0.0
    lost_prob: float = 0.0
    timeout_prob: float = 0.0


@dataclass
class Observation:
    pos: tuple[int, int]
    target: tuple[int, int]
    last_status: str
    tick: int


class GridWorld:
    """模拟环境：网格、墙、目标；可注入漂移/丢失/超时。"""

    def __init__(
        self,
        size: int = 20,
        start: tuple[int, int] = (1, 1),
        target: tuple[int, int] = (15, 15),
        walls: set[tuple[int, int]] | None = None,
        faults: Faults | None = None,
        seed: int = 0,
    ) -> None:
        self.size = size
        self.start = start
        self.pos = start
        self.target = target
        self.walls = walls or set()
        self.faults = faults or Faults()
        self.rng = random.Random(seed)
        self.tick = 0
        self.last_status = "start"

    def observe(self) -> Observation:
        return Observation(pos=self.pos, target=self.target, last_status=self.last_status, tick=self.tick)

    def in_bounds(self, cell: tuple[int, int]) -> bool:
        return 0 <= cell[0] < self.size and 0 <= cell[1] < self.size

    def passable(self, cell: tuple[int, int]) -> bool:
        return self.in_bounds(cell) and cell not in self.walls

    def execute(self, action: str, cell: tuple[int, int] | None = None) -> str:
        self.tick += 1
        if self.rng.random() < self.faults.timeout_prob:
            self.last_status = "timeout"
            return self.last_status
        if self.rng.random() < self.faults.lost_prob:
            self.last_status = "lost"
            return self.last_status
        if action == "interact":
            if self.pos == self.target:
                self.last_status = "ok"
            else:
                self.last_status = "too_far"
            return self.last_status
        if action == "move" and cell is not None:
            if not self.passable(cell):
                self.last_status = "blocked"
                return self.last_status
            if self.rng.random() < self.faults.drift_prob:
                # 漂移到相邻可走格
                candidates = [
                    (cell[0] + dx, cell[1] + dy)
                    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))
                    if self.passable((cell[0] + dx, cell[1] + dy))
                ]
                if candidates:
                    self.pos = self.rng.choice(candidates)
                    self.last_status = "drift"
                    return self.last_status
            self.pos = cell
            self.last_status = "ok"
            return self.last_status
        self.last_status = "bad_action"
        return self.last_status


def astar(
    start: tuple[int, int], goal: tuple[int, int], passable: Callable[[tuple[int, int]], bool]
) -> list[tuple[int, int]]:
    """四方向 A*；返回不含起点的路径。"""
    if start == goal:
        return []
    open_heap: list[tuple[int, tuple[int, int]]] = [(0, start)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    cost: dict[tuple[int, int], int] = {start: 0}
    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = came[current]
            return list(reversed(path))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (current[0] + dx, current[1] + dy)
            if not passable(nxt):
                continue
            new_cost = cost[current] + 1
            if new_cost < cost.get(nxt, 1 << 30):
                cost[nxt] = new_cost
                priority = new_cost + abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])
                heapq.heappush(open_heap, (priority, nxt))
                came[nxt] = current
    return []


@dataclass
class SafetyPolicy:
    max_retries_per_step: int = 3
    max_total_retries: int = 20


class SafetySupervisor:
    def __init__(self, policy: SafetyPolicy) -> None:
        self.policy = policy
        self.stop_requested = False
        self.total_retries = 0
        self.high_risk_approved = False

    def request_stop(self) -> None:
        self.stop_requested = True

    def approve_high_risk(self) -> None:
        self.high_risk_approved = True

    def can_retry(self, step: Step) -> bool:
        return (
            step.attempts < min(step.max_retries, self.policy.max_retries_per_step)
            and self.total_retries < self.policy.max_total_retries
        )

    def may_execute(self, step: Step) -> tuple[bool, str]:
        if self.stop_requested:
            return False, "人工停止"
        if step.risk == Risk.HIGH and not self.high_risk_approved:
            return False, "高风险动作未获确认"
        if step.requires_confirmation and not self.high_risk_approved:
            return False, "需要人工确认"
        return True, ""


class Outcome(str, Enum):
    DONE = "done"
    L1_ADJUST = "l1_adjust"
    L2_REPLAN_STEP = "l2_replan_step"
    L3_REPLAN_PLAN = "l3_replan_plan"
    L4_PAUSE = "l4_pause"


@dataclass
class ExecReport:
    completed: bool = False
    paused_reason: str = ""
    ticks: int = 0
    actions: int = 0
    retries: int = 0
    replans: int = 0
    pauses: int = 0
    level_events: dict[str, int] = field(default_factory=dict)
    first_try_success: int = 0
    steps_done: int = 0
    steps_total: int = 0

    def bump(self, key: str) -> None:
        self.level_events[key] = self.level_events.get(key, 0) + 1


class Executor:
    """执行循环：观察 → 校验 → 短动作 → 观察结果 → 成功/纠错/暂停。"""

    def __init__(
        self,
        world: GridWorld,
        safety: SafetySupervisor,
        max_ticks: int = 500,
        audit: "AuditLog | None" = None,
        checkpoint_path: str | None = None,
    ) -> None:
        self.world = world
        self.safety = safety
        self.max_ticks = max_ticks
        self.audit = audit
        self.checkpoint_path = checkpoint_path

    def run(self, plan: Plan, report: ExecReport | None = None, max_steps: int | None = None) -> ExecReport:
        report = report or ExecReport()
        report.steps_total = len(plan.steps)
        path: list[tuple[int, int]] = []
        while plan.current() is not None and report.ticks < self.max_ticks:
            if max_steps is not None and report.steps_done >= max_steps:
                report.paused_reason = "达到 max_steps（模拟中断）"
                return report
            if self.safety.stop_requested:
                report.paused_reason = "人工停止"
                report.pauses += 1
                return report
            step = plan.current()
            ok, reason = self.safety.may_execute(step)
            if not ok:
                report.paused_reason = reason
                report.pauses += 1
                return report
            # 每次循环都重新观察真实环境（恢复/纠错都以此为准）
            obs = self.world.observe()
            report.ticks = obs.tick
            goal = step.target if step.target is not None else obs.target
            if step.action == "interact" and obs.pos != goal:
                # 恢复/前置条件不满足：先重新走到交互点（L3 局部重规划）
                report.bump("l3_need_move")
                if not path:
                    path = astar(obs.pos, goal, self.world.passable)
                if not path:
                    report.paused_reason = "无法到达交互点"
                    report.pauses += 1
                    return report
                nxt2 = path.pop(0)
                status2 = self.world.execute("move", nxt2)
                report.actions += 1
                if self.audit:
                    self.audit.record(tick=self.world.tick, step=step.id, action="move", status=status2, from_pos=list(obs.pos), pos=list(self.world.pos))
                if status2 in ("ok", "drift"):
                    if status2 == "drift":
                        report.bump("l1_drift")
                        path = []
                    continue
                result2 = self._handle_failure(step, report, status2)
                path = []
                if result2 == Outcome.L4_PAUSE:
                    report.paused_reason = f"恢复移动失败：{status2}"
                    report.pauses += 1
                    return report
                continue
            if step.action == "interact":
                status = "ok" if obs.pos == goal else "too_far"
                report.actions += 1
                if self.audit:
                    self.audit.record(tick=obs.tick, step=step.id, action="interact", status=status, pos=list(obs.pos))
                if status == "ok":
                    step.status = StepStatus.DONE
                    report.first_try_success += 1 if step.attempts == 0 else 0
                    report.steps_done += 1
                    plan.advance()
                    self._save_checkpoint(plan, self.world.observe())
                    continue
                result = self._handle_failure(step, report, "interact_failed")
                if result == Outcome.L4_PAUSE:
                    report.paused_reason = "连续交互失败"
                    report.pauses += 1
                    return report
                continue
            # move：按当前真实位置重算路径（检查点恢复后不依赖旧状态）
            if obs.pos == goal:
                step.status = StepStatus.DONE
                report.steps_done += 1
                path = []
                plan.advance()
                self._save_checkpoint(plan, obs)
                continue
            if not path:
                path = astar(obs.pos, goal, self.world.passable)
                if not path:
                    report.paused_reason = "无可行路径"
                    report.pauses += 1
                    return report
                report.replans += 1
            nxt = path[0]
            status = self.world.execute("move", nxt)
            report.actions += 1
            if self.audit:
                self.audit.record(tick=self.world.tick, step=step.id, action="move", status=status, from_pos=list(obs.pos), pos=list(self.world.pos))
            if status in ("ok", "drift"):
                if status == "drift":
                    report.bump("l1_drift")
                    if step.attempts == 0:
                        step.attempts += 1
                        report.retries += 1
                        self.safety.total_retries += 1
                    path = []  # 位置变了，重算
                else:
                    path.pop(0) if path and path[0] == nxt else path.clear()
                    if step.attempts == 0:
                        step.first_try_ok = True
                    step.attempts = 0  # 有推进就重置连续失败计数
                    if not path:
                        step.status = StepStatus.DONE
                        report.steps_done += 1
                        plan.advance()
                        self._save_checkpoint(plan, self.world.observe())
                continue
            result = self._handle_failure(step, report, status)
            if result == Outcome.L4_PAUSE:
                report.paused_reason = f"连续失败：{status}"
                report.pauses += 1
                return report
            path = []
            if result == Outcome.L3_REPLAN_PLAN:
                report.replans += 1
        report.completed = plan.current() is None
        return report

    def _save_checkpoint(self, plan: "Plan", obs: Observation) -> None:
        if not self.checkpoint_path:
            return
        CheckpointStore.save(
            self.checkpoint_path,
            {"plan_index": plan.index, "tick": obs.tick, "pos": list(obs.pos)},
        )

    def _handle_failure(self, step: Step, report: ExecReport, status: str) -> Outcome:
        step.attempts += 1
        self.safety.total_retries += 1
        report.retries += 1
        if status in ("timeout", "lost"):
            report.bump("l2_action_lost")
            if self.safety.can_retry(step):
                return Outcome.L2_REPLAN_STEP
            return Outcome.L4_PAUSE
        if status == "blocked":
            report.bump("l2_blocked")
            if self.safety.can_retry(step):
                return Outcome.L2_REPLAN_STEP
            return Outcome.L3_REPLAN_PLAN
        report.bump("l2_other")
        if self.safety.can_retry(step):
            return Outcome.L1_ADJUST
        return Outcome.L4_PAUSE

class AuditLog:
    """审计日志：每个动作一行 JSONL，可回放。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def record(self, **fields) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(fields, ensure_ascii=False) + "\n")


class CheckpointStore:
    @staticmethod
    def save(path: str | Path, data: dict) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> dict | None:
        target = Path(path)
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))


@dataclass
class Task:
    id: str
    plan: Plan
    deps: list[str] = field(default_factory=list)


def topological_order(tasks: list[Task]) -> list[Task]:
    """按依赖排序；存在环时抛错。"""
    by_id = {task.id: task for task in tasks}
    remaining = set(by_id)
    ordered: list[Task] = []
    while remaining:
        ready = [tid for tid in remaining if not (set(by_id[tid].deps) & remaining)]
        if not ready:
            raise ValueError("任务依赖存在环")
        for tid in sorted(ready):
            ordered.append(by_id[tid])
            remaining.discard(tid)
    return ordered

class TaskRunner:
    """按依赖顺序执行多个任务；失败即停，后续任务跳过；支持从检查点恢复。"""

    def __init__(
        self,
        world: GridWorld,
        safety: SafetySupervisor,
        audit: "AuditLog | None" = None,
        checkpoint_path: str | None = None,
    ) -> None:
        self.world = world
        self.safety = safety
        self.audit = audit
        self.checkpoint_path = checkpoint_path

    def run(self, tasks: list[Task]) -> dict:
        order = topological_order(tasks)
        status = {task.id: "pending" for task in tasks}
        resume = CheckpointStore.load(self.checkpoint_path) if self.checkpoint_path else None
        start = 0
        if resume and resume.get("task_id") in [t.id for t in order]:
            start = [t.id for t in order].index(resume["task_id"])
            for task in order[:start]:
                status[task.id] = "done"
        for task in order[start:]:
            if any(status[dep] != "done" for dep in task.deps):
                status[task.id] = "skipped"
                continue
            plan = task.plan
            plan.index = 0
            if resume and task.id == resume.get("task_id"):
                plan.index = min(int(resume.get("plan_index", 0)), len(plan.steps))
            if plan.index >= len(plan.steps):
                status[task.id] = "done"
                continue
            report = Executor(self.world, self.safety, audit=self.audit).run(plan, ExecReport())
            if report.completed:
                status[task.id] = "done"
                if self.checkpoint_path:
                    CheckpointStore.save(
                        self.checkpoint_path, {"task_id": task.id, "plan_index": len(plan.steps)}
                    )
            else:
                status[task.id] = "failed"
                if self.checkpoint_path:
                    CheckpointStore.save(
                        self.checkpoint_path, {"task_id": task.id, "plan_index": plan.index}
                    )
                break
        for task in order:
            if status[task.id] == "pending":
                status[task.id] = "skipped"
        return status