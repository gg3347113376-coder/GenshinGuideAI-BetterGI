"""方向一事件 → 执行计划 → 模拟执行，验证「视频→计划→执行」链路。

用法：
  python tools/run_from_events.py --project runs\p002_full_v7.json --max-events 12
"""
from __future__ import annotations

import argparse
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
    SafetyPolicy,
    SafetySupervisor,
    Task,
    topological_order,
)
from ggai.plan_builder import plan_from_events  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--max-events", type=int, default=12)
    parser.add_argument("--audit", default="runs/exec_audit.jsonl")
    parser.add_argument("--checkpoint", default="runs/exec_checkpoint.json")
    parser.add_argument("--drift", type=float, default=0.0)
    parser.add_argument("--lost", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=0.0)
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    plan, meta = plan_from_events(project, max_events=args.max_events)
    # 战略层：两个任务，第二个依赖第一个（演示依赖图）
    tasks = [
        Task(id="t1", plan=plan),
        Task(id="t2", plan=type(plan)(steps=[]), deps=["t1"]),
    ]
    order = topological_order(tasks)
    world = GridWorld(
        target=(15, 15),
        faults=Faults(drift_prob=args.drift, lost_prob=args.lost, timeout_prob=args.timeout),
        seed=11,
    )
    safety = SafetySupervisor(SafetyPolicy(max_total_retries=80))
    audit = AuditLog(ROOT / args.audit)
    executor = Executor(world, safety, max_ticks=5000, audit=audit, checkpoint_path=str(ROOT / args.checkpoint))
    report = executor.run(plan, ExecReport())
    checkpoint = CheckpointStore.load(ROOT / args.checkpoint)
    # 导出沙盘回放数据
    records = []
    audit_path = ROOT / args.audit
    if audit_path.exists():
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    replay = {
        "project": project.get("project", {}).get("name", ""),
        "note": "网格坐标示意回放；不是视频真实坐标",
        "steps": records,
    }
    replay_path = ROOT / "sandbox" / "data" / "exec_replay.json"
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    result = {
        "project": project.get("project", {}).get("name", ""),
        "meta": meta,
        "task_order": [t.id for t in order],
        "completed": report.completed,
        "paused_reason": report.paused_reason,
        "steps_done": report.steps_done,
        "actions": report.actions,
        "retries": report.retries,
        "checkpoint": checkpoint,
        "audit_lines": len((ROOT / args.audit).read_text(encoding="utf-8").splitlines()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
