"""多任务依赖链执行 + 失败中断 + 恢复演示。

用法：python tools/run_task_chain.py
"""
from __future__ import annotations

import json
import sys
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


def make_task(task_id: str, target: tuple[int, int], deps: list[str] | None = None) -> Task:
    return Task(
        id=task_id,
        deps=deps or [],
        plan=Plan(
            steps=[
                Step(id=f"{task_id}_go", goal=f"到 {target}", action="move", expected="到达", target=target),
                Step(id=f"{task_id}_do", goal=f"在 {target} 交互", action="interact", expected="成功", target=target),
            ]
        ),
    )


def enclosed(target: tuple[int, int]) -> set[tuple[int, int]]:
    x, y = target
    return {(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)}


def main() -> int:
    checkpoint = ROOT / "runs" / "chain_checkpoint.json"
    if checkpoint.exists():
        checkpoint.unlink()
    tasks = [
        make_task("t1_采集", (5, 5)),
        make_task("t2_营地", (18, 18), deps=["t1_采集"]),
        make_task("t3_返回", (10, 10), deps=["t2_营地"]),
    ]
    world1 = GridWorld(target=(10, 10), walls=enclosed((18, 18)), seed=0)
    status1 = TaskRunner(world1, SafetySupervisor(SafetyPolicy()), checkpoint_path=str(checkpoint)).run(tasks)
    cp = CheckpointStore.load(checkpoint)

    # 修复环境（移除墙）+ 玩家起点变化，然后恢复
    world2 = GridWorld(target=(10, 10), start=(2, 2), seed=1)
    status2 = TaskRunner(world2, SafetySupervisor(SafetyPolicy()), checkpoint_path=str(checkpoint)).run(tasks)

    print(
        json.dumps(
            {
                "first_run": status1,
                "checkpoint_after_failure": cp,
                "resume_run": status2,
                "note": "仅模拟环境；恢复时重新观察世界并重走路径",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
