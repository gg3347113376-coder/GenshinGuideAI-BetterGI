"""mock 驱动闭环演示：正常 / 漂移 / 丢失 / 阻塞 / 超时。

用法：python tools\run_mock_driver.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.driver import MockGameDriver  # noqa: E402
from ggai.executor import (  # noqa: E402
    AuditLog,
    Executor,
    Faults,
    Plan,
    SafetyPolicy,
    SafetySupervisor,
    Step,
)


def build_plan() -> Plan:
    return Plan(
        steps=[
            Step(id="s1", goal="到达目标", action="move", expected="pos==target", target=(15, 15)),
            Step(id="s2", goal="交互", action="interact", expected="ok", target=(15, 15)),
        ]
    )


SCENARIOS = {
    "clean": dict(faults=Faults(), walls=None),
    "drift": dict(faults=Faults(drift_prob=0.25), walls=None),
    "lost": dict(faults=Faults(lost_prob=0.20), walls=None),
    "timeout": dict(faults=Faults(timeout_prob=0.20), walls=None),
    "blocked": dict(
        faults=Faults(),
        walls={(x, 5) for x in range(0, 20)} | {(x, 6) for x in range(0, 20)},
    ),
}


def main() -> int:
    results = []
    for name, spec in SCENARIOS.items():
        driver = MockGameDriver(seed=7, **spec)
        audit = AuditLog(ROOT / "runs" / f"mock_{name}_audit.jsonl")
        executor = Executor(driver, SafetySupervisor(SafetyPolicy()), max_ticks=600, audit=audit)
        report = executor.run(build_plan())
        results.append(
            {
                "scenario": name,
                "completed": report.completed,
                "steps_done": report.steps_done,
                "steps_total": report.steps_total,
                "ticks": report.ticks,
                "actions": report.actions,
                "retries": report.retries,
                "pauses": report.pauses,
                "paused_reason": report.paused_reason,
                "level_events": report.level_events,
                "final_pos": list(driver.pos),
                "observation": driver.describe(),
            }
        )
        print(json.dumps(results[-1], ensure_ascii=False))

    out = ROOT / "runs" / "mock_driver.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
