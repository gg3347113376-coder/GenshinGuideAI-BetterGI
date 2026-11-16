import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.executor import (  # noqa: E402
    CheckpointStore,
    GridWorld,
    Plan,
    SafetyPolicy,
    SafetySupervisor,
    Step,
    Task,
    TaskRunner,
)


def task_move_interact(task_id: str, target: tuple[int, int], deps: list[str] | None = None) -> Task:
    plan = Plan(
        steps=[
            Step(id=f"{task_id}_go", goal=f"到 {target}", action="move", expected="到达", target=target),
            Step(id=f"{task_id}_do", goal=f"在 {target} 交互", action="interact", expected="成功", target=target),
        ]
    )
    return Task(id=task_id, plan=plan, deps=deps or [])


def enclosed_walls(target: tuple[int, int]) -> set[tuple[int, int]]:
    x, y = target
    return {(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)}


class TaskRunnerTests(unittest.TestCase):
    def test_chain_completes_in_order(self):
        world = GridWorld(target=(10, 10), seed=0)
        tasks = [task_move_interact("t1", (5, 5)), task_move_interact("t2", (10, 10), deps=["t1"])]
        status = TaskRunner(world, SafetySupervisor(SafetyPolicy())).run(tasks)
        self.assertEqual(status, {"t1": "done", "t2": "done"})

    def test_failure_skips_dependents(self):
        # t2 的目标被墙围死 → 失败；t3 依赖 t2 → 跳过
        walls = enclosed_walls((18, 18))
        world = GridWorld(target=(10, 10), walls=walls, seed=0)
        tasks = [
            task_move_interact("t1", (5, 5)),
            task_move_interact("t2", (18, 18), deps=["t1"]),
            task_move_interact("t3", (10, 10), deps=["t2"]),
        ]
        status = TaskRunner(world, SafetySupervisor(SafetyPolicy())).run(tasks)
        self.assertEqual(status["t1"], "done")
        self.assertEqual(status["t2"], "failed")
        self.assertEqual(status["t3"], "skipped")

    def test_resume_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "chain.json"
            world1 = GridWorld(target=(10, 10), walls=enclosed_walls((18, 18)), seed=0)
            tasks1 = [
                task_move_interact("t1", (5, 5)),
                task_move_interact("t2", (18, 18), deps=["t1"]),
            ]
            status1 = TaskRunner(
                world1, SafetySupervisor(SafetyPolicy()), checkpoint_path=str(checkpoint)
            ).run(tasks1)
            self.assertEqual(status1["t2"], "failed")
            cp = CheckpointStore.load(checkpoint)
            self.assertEqual(cp["task_id"], "t2")

            # 恢复：环境修复（墙移除），玩家起点也变了
            world2 = GridWorld(target=(10, 10), start=(2, 2), seed=1)
            tasks2 = [
                task_move_interact("t1", (5, 5)),
                task_move_interact("t2", (18, 18), deps=["t1"]),
            ]
            status2 = TaskRunner(
                world2, SafetySupervisor(SafetyPolicy()), checkpoint_path=str(checkpoint)
            ).run(tasks2)
            self.assertEqual(status2["t1"], "done")  # 从检查点恢复时视为已完成
            self.assertEqual(status2["t2"], "done")


if __name__ == "__main__":
    unittest.main()
