"""检查点恢复演示：中断后必须重新观察环境，不能依赖历史位置。

用法：python tools/resume_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.executor import (  # noqa: E402
    AuditLog,
    CheckpointStore,
    ExecReport,
    Executor,
    Faults,
    GridWorld,
    Plan,
    SafetyPolicy,
    SafetySupervisor,
    Step,
)


def make_plan() -> Plan:
    return Plan(
        steps=[
            Step(id="s1", goal="走到目标", action="move", expected="到达目标格"),
            Step(id="s2", goal="交互", action="interact", expected="交互成功"),
        ]
    )


def main() -> int:
    audit_path = ROOT / "runs" / "resume_audit.jsonl"
    checkpoint_path = ROOT / "runs" / "resume_checkpoint.json"
    # 第一次运行：只走 1 步就中断
    world = GridWorld(target=(15, 15), seed=1)
    safety = SafetySupervisor(SafetyPolicy(max_total_retries=80))
    audit = AuditLog(audit_path)
    executor = Executor(world, safety, audit=audit, checkpoint_path=str(checkpoint_path))
    first = executor.run(make_plan(), ExecReport(), max_steps=1)
    checkpoint = CheckpointStore.load(checkpoint_path)

    # 模拟“停机期间环境变化”：玩家被移到别处，路上多了一段墙
    world2 = GridWorld(
        target=(15, 15),
        start=(10, 2),
        walls={(12, y) for y in range(0, 12)},
        faults=Faults(drift_prob=0.0),
        seed=2,
    )
    plan2 = Plan(steps=make_plan().steps, index=int(checkpoint["plan_index"]))
    safety2 = SafetySupervisor(SafetyPolicy(max_total_retries=80))
    audit2 = AuditLog(ROOT / "runs" / "resume_audit2.jsonl")
    second = Executor(world2, safety2, audit=audit2, checkpoint_path=str(checkpoint_path)).run(plan2, ExecReport())

    result = {
        "first_run": {
            "steps_done": first.steps_done,
            "stopped": first.paused_reason,
            "checkpoint": checkpoint,
        },
        "world_changed": {
            "start_pos": list(world2.start),
            "checkpoint_pos": checkpoint["pos"] if checkpoint else None,
            "same": checkpoint is not None and list(world2.start) == checkpoint["pos"],
            "walls": len(world2.walls),
        },
        "resume": {
            "completed": second.completed,
            "steps_done": second.steps_done,
            "actions": second.actions,
            "replans": second.replans,
            "paused_reason": second.paused_reason,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
