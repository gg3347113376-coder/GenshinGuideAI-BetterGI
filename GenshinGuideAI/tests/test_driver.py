import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.driver import MockGameDriver  # noqa: E402
from ggai.executor import Executor, Faults, Plan, SafetyPolicy, SafetySupervisor, Step  # noqa: E402


def plan() -> Plan:
    return Plan(
        steps=[
            Step(id="s1", goal="到达", action="move", expected="ok", target=(15, 15)),
            Step(id="s2", goal="交互", action="interact", expected="ok", target=(15, 15)),
        ]
    )


def run(driver: MockGameDriver) -> object:
    return Executor(driver, SafetySupervisor(SafetyPolicy()), max_ticks=600).run(plan())


class DriverTests(unittest.TestCase):
    def test_clean_completes(self):
        driver = MockGameDriver(seed=1)
        report = run(driver)
        self.assertTrue(report.completed)
        self.assertEqual(driver.pos, (15, 15))
        self.assertEqual(report.retries, 0)

    def test_observe_contract(self):
        driver = MockGameDriver(seed=1)
        obs = driver.observe()
        self.assertEqual(obs.pos, (1, 1))
        self.assertEqual(driver.describe()["driver"], "mock")

    def test_blocked_pauses(self):
        walls = {(x, 5) for x in range(20)} | {(x, 6) for x in range(20)}
        driver = MockGameDriver(walls=walls, seed=1)
        report = run(driver)
        self.assertFalse(report.completed)
        self.assertIn("无可行路径", report.paused_reason)

    def test_drift_retries_but_completes(self):
        driver = MockGameDriver(faults=Faults(drift_prob=0.25), seed=7)
        report = run(driver)
        self.assertTrue(report.completed)
        self.assertGreater(report.retries, 0)
        self.assertGreater(report.level_events.get("l1_drift", 0), 0)

    def test_lost_pauses_after_retries(self):
        driver = MockGameDriver(faults=Faults(lost_prob=0.25), seed=7)
        report = run(driver)
        self.assertFalse(report.completed)
        self.assertGreater(report.pauses, 0)


if __name__ == "__main__":
    unittest.main()
