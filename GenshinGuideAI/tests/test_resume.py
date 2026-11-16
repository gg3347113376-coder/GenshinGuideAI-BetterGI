import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.executor import (  # noqa: E402
    AuditLog,
    CheckpointStore,
    ExecReport,
    Executor,
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


class ResumeTests(unittest.TestCase):
    def test_max_steps_stops_and_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "cp.json"
            world = GridWorld(target=(15, 15), seed=1)
            report = Executor(
                world, SafetySupervisor(SafetyPolicy()), checkpoint_path=str(checkpoint)
            ).run(make_plan(), ExecReport(), max_steps=1)
            self.assertFalse(report.completed)
            self.assertEqual(report.steps_done, 1)
            data = CheckpointStore.load(checkpoint)
            self.assertIsNotNone(data)
            self.assertEqual(data["plan_index"], 1)

    def test_resume_reobserves_changed_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "cp.json"
            audit1 = AuditLog(Path(tmp) / "a1.jsonl")
            world1 = GridWorld(target=(15, 15), seed=1)
            first = Executor(
                world1, SafetySupervisor(SafetyPolicy()), audit=audit1, checkpoint_path=str(checkpoint)
            ).run(make_plan(), ExecReport(), max_steps=1)
            self.assertEqual(first.steps_done, 1)
            cp = CheckpointStore.load(checkpoint)

            # 停机期间：玩家被移到 (10, 2)，并新增一道墙
            audit2 = AuditLog(Path(tmp) / "a2.jsonl")
            world2 = GridWorld(
                target=(15, 15), start=(10, 2), walls={(12, y) for y in range(0, 12)}, seed=2
            )
            plan2 = Plan(steps=make_plan().steps, index=int(cp["plan_index"]))
            second = Executor(
                world2, SafetySupervisor(SafetyPolicy(max_total_retries=80)), audit=audit2
            ).run(plan2, ExecReport())
            self.assertTrue(second.completed, second.paused_reason)
            self.assertNotEqual(list(world2.start), cp["pos"])
            # 审计第一条动作必须来自新观察的位置，而不是检查点里的旧位置
            lines = [json.loads(x) for x in (Path(tmp) / "a2.jsonl").read_text().splitlines() if x]
            self.assertTrue(lines)
            self.assertEqual(lines[0]["from_pos"], [10, 2])


if __name__ == "__main__":
    unittest.main()
