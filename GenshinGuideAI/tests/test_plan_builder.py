import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.executor import (  # noqa: E402
    CheckpointStore,
    ExecReport,
    Executor,
    GridWorld,
    Plan,
    SafetyPolicy,
    SafetySupervisor,
    Task,
    topological_order,
)
from ggai.plan_builder import plan_from_events  # noqa: E402


def sample_project():
    return {
        "events": [
            {"action": {"type": "move", "params": {"quest_text": "前往目标"}}},
            {"action": {"type": "dialogue", "params": {"text": "你好"}}},
            {"action": {"type": "move", "params": {"quest_text": "继续前进"}}},
            {"action": {"type": "dialogue", "params": {"text": "再见"}}},
        ]
    }


class PlanBuilderTests(unittest.TestCase):
    def test_plan_shape(self):
        plan, meta = plan_from_events(sample_project())
        self.assertEqual(meta["events_used"], 4)
        self.assertEqual(len(plan.steps), 4)
        self.assertEqual(plan.steps[0].action, "move")
        self.assertEqual(plan.steps[1].action, "interact")
        self.assertIsNotNone(plan.steps[0].target)

    def test_plan_runs_to_completion(self):
        plan, _ = plan_from_events(sample_project())
        world = GridWorld(start=(1, 1), target=(15, 15))
        report = Executor(world, SafetySupervisor(SafetyPolicy()), max_ticks=500).run(plan, ExecReport())
        self.assertTrue(report.completed, report.paused_reason)
        self.assertEqual(report.steps_done, 4)

    def test_topological_order(self):
        tasks = [
            Task(id="b", plan=Plan(), deps=["a"]),
            Task(id="a", plan=Plan()),
            Task(id="c", plan=Plan(), deps=["b"]),
        ]
        order = [t.id for t in topological_order(tasks)]
        self.assertEqual(order, ["a", "b", "c"])

    def test_cycle_raises(self):
        tasks = [Task(id="a", plan=Plan(), deps=["b"]), Task(id="b", plan=Plan(), deps=["a"])]
        with self.assertRaises(ValueError):
            topological_order(tasks)

    def test_checkpoint_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cp.json"
            plan, _ = plan_from_events(sample_project())
            world = GridWorld(start=(1, 1), target=(15, 15))
            Executor(
                world, SafetySupervisor(SafetyPolicy()), max_ticks=500, checkpoint_path=str(path)
            ).run(plan, ExecReport())
            data = CheckpointStore.load(path)
            self.assertIsNotNone(data)
            self.assertIn("plan_index", data)
            self.assertEqual(data["plan_index"], 4)


if __name__ == "__main__":
    unittest.main()
