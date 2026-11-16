import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.executor import (  # noqa: E402
    ExecReport,
    Executor,
    Faults,
    GridWorld,
    Plan,
    Risk,
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


class ExecutorTests(unittest.TestCase):
    def test_clean_run_completes(self):
        world = GridWorld(target=(5, 5))
        safety = SafetySupervisor(SafetyPolicy())
        report = Executor(world, safety).run(make_plan(), ExecReport())
        self.assertTrue(report.completed)
        self.assertEqual(report.steps_done, 2)
        self.assertGreater(report.actions, 0)
        self.assertEqual(report.pauses, 0)

    def test_wall_detour(self):
        # 竖直墙，留一个缺口
        walls = {(3, y) for y in range(0, 10)}
        world = GridWorld(target=(6, 5), walls=walls)
        safety = SafetySupervisor(SafetyPolicy())
        report = Executor(world, safety).run(make_plan(), ExecReport())
        self.assertTrue(report.completed, report.paused_reason)

    def test_drift_is_recovered(self):
        world = GridWorld(target=(8, 8), faults=Faults(drift_prob=0.25), seed=7)
        safety = SafetySupervisor(SafetyPolicy(max_total_retries=50))
        report = Executor(world, safety).run(make_plan(), ExecReport())
        self.assertTrue(report.completed, report.paused_reason)
        self.assertGreaterEqual(report.level_events.get("l1_drift", 0), 1)

    def test_action_lost_retries(self):
        world = GridWorld(target=(5, 5), faults=Faults(lost_prob=0.5), seed=3)
        safety = SafetySupervisor(SafetyPolicy(max_total_retries=50))
        report = Executor(world, safety).run(make_plan(), ExecReport())
        self.assertTrue(report.completed, report.paused_reason)
        self.assertGreater(report.retries, 0)

    def test_always_timeout_pauses(self):
        world = GridWorld(target=(5, 5), faults=Faults(timeout_prob=1.0), seed=1)
        safety = SafetySupervisor(SafetyPolicy())
        report = Executor(world, safety).run(make_plan(), ExecReport())
        self.assertFalse(report.completed)
        self.assertGreaterEqual(report.pauses, 1)

    def test_manual_stop(self):
        world = GridWorld(target=(5, 5))
        safety = SafetySupervisor(SafetyPolicy())
        safety.request_stop()
        report = Executor(world, safety).run(make_plan(), ExecReport())
        self.assertFalse(report.completed)
        self.assertEqual(report.paused_reason, "人工停止")

    def test_high_risk_requires_confirmation(self):
        plan = Plan(steps=[Step(id="h1", goal="危险动作", action="interact", expected="ok", risk=Risk.HIGH)])
        world = GridWorld(start=(1, 1), target=(1, 1))
        safety = SafetySupervisor(SafetyPolicy())
        report = Executor(world, safety).run(plan, ExecReport())
        self.assertFalse(report.completed)
        self.assertIn("高风险", report.paused_reason)
        safety2 = SafetySupervisor(SafetyPolicy())
        safety2.approve_high_risk()
        report2 = Executor(GridWorld(start=(1, 1), target=(1, 1)), safety2).run(
            Plan(steps=[Step(id="h1", goal="危险动作", action="interact", expected="ok", risk=Risk.HIGH)]),
            ExecReport(),
        )
        self.assertTrue(report2.completed)


if __name__ == "__main__":
    unittest.main()
