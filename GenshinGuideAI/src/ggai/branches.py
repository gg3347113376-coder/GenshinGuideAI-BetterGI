"""方向二 P5：自由推演分支——同一初始状态下比较不同路线/参数。

记录：初始状态、路线参数、规则版本、随机种子、修改内容、结果与不确定性。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field, replace

from .executor import (
    ExecReport,
    Executor,
    Faults,
    GridWorld,
    Plan,
    SafetyPolicy,
    SafetySupervisor,
    Step,
)


@dataclass
class BranchSpec:
    id: str
    name: str
    nodes: list[tuple[int, int]]
    start: tuple[int, int] = (1, 1)
    target: tuple[int, int] = (15, 15)
    walls: set[tuple[int, int]] = field(default_factory=set)
    faults: Faults = field(default_factory=Faults)
    seed: int = 0
    rules_version: str = "rules-v1"
    changes: str = ""


def build_plan(nodes: list[tuple[int, int]]) -> Plan:
    steps: list[Step] = []
    for index, (x, z) in enumerate(nodes, 1):
        steps.append(Step(id=f"b{index}_move", goal=f"到 ({x},{z})", action="move", expected="到达", target=(x, z)))
        steps.append(Step(id=f"b{index}_do", goal=f"在 ({x},{z}) 交互", action="interact", expected="成功", target=(x, z)))
    return Plan(steps=steps)


def check_constraints(spec: BranchSpec) -> list[str]:
    problems = []
    for node in spec.nodes:
        if not (0 <= node[0] < 20 and 0 <= node[1] < 20):
            problems.append(f"节点越界：{node}")
        elif node in spec.walls:
            problems.append(f"节点在墙里：{node}")
    if not spec.nodes:
        problems.append("路线为空")
    return problems


def run_branch(spec: BranchSpec) -> dict:
    problems = check_constraints(spec)
    if problems:
        return {
            "id": spec.id,
            "name": spec.name,
            "valid": False,
            "problems": problems,
            "completed": False,
        }
    world = GridWorld(
        start=spec.start,
        target=spec.target,
        walls=set(spec.walls),
        faults=spec.faults,
        seed=spec.seed,
    )
    report = Executor(world, SafetySupervisor(SafetyPolicy(max_total_retries=80)), max_ticks=5000).run(
        build_plan(spec.nodes), ExecReport()
    )
    return {
        "id": spec.id,
        "name": spec.name,
        "valid": True,
        "completed": report.completed,
        "steps_done": report.steps_done,
        "actions": report.actions,
        "retries": report.retries,
        "ticks": report.ticks,
        "replans": report.replans,
        "pauses": report.pauses,
        "level_events": report.level_events,
        "paused_reason": report.paused_reason,
        "seed": spec.seed,
        "rules_version": spec.rules_version,
        "changes": spec.changes,
        "initial_state": {
            "start": list(spec.start),
            "target": list(spec.target),
            "walls": sorted(spec.walls),
            "faults": {
                "drift_prob": spec.faults.drift_prob,
                "lost_prob": spec.faults.lost_prob,
                "timeout_prob": spec.faults.timeout_prob,
            },
        },
        "nodes": [list(n) for n in spec.nodes],
    }


def compare(branches: list[BranchSpec]) -> dict:
    results = [run_branch(branch) for branch in branches]
    valid = [r for r in results if r.get("valid")]
    winner = None
    if valid:
        winner = sorted(
            valid,
            key=lambda r: (not r["completed"], r["actions"], r["ticks"]),
        )[0]["id"]
    return {
        "branches": results,
        "winner": winner,
        "note": "仅在模拟环境比较；不确定性来自随机种子与故障注入",
    }


def evaluate(spec: BranchSpec, seeds: list[int]) -> dict:
    """同一分支跑多个种子，给出完成率与指标均值/标准差。"""
    runs = []
    for seed in seeds:
        run = run_branch(replace(spec, seed=seed))
        run["seed"] = seed
        runs.append(run)
    valid = [r for r in runs if r.get("valid")]
    actions = [r["actions"] for r in valid]
    retries = [r["retries"] for r in valid]
    ticks = [r["ticks"] for r in valid]
    completed = [1.0 if r["completed"] else 0.0 for r in valid]
    return {
        "id": spec.id,
        "name": spec.name,
        "seeds": list(seeds),
        "runs": runs,
        "valid_runs": len(valid),
        "completion_rate": round(sum(completed) / len(completed), 3) if completed else 0.0,
        "actions_mean": round(statistics.mean(actions), 2) if actions else 0.0,
        "actions_std": round(statistics.pstdev(actions), 2) if len(actions) > 1 else 0.0,
        "retries_mean": round(statistics.mean(retries), 2) if retries else 0.0,
        "ticks_mean": round(statistics.mean(ticks), 2) if ticks else 0.0,
    }