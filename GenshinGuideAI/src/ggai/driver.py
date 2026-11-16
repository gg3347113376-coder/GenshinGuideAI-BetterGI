"""执行驱动接口与 mock 游戏环境。

真实环境（B）只允许只读观测；在接入前，用 MockGameDriver 在受控网格里
验证「观察 → 动作 → 再观察 → 纠错」闭环。Executor 只依赖以下鸭子类型：

    observe() -> Observation
    passable(cell) -> bool
    execute(action, cell=None) -> str
    pos / tick 属性
"""
from __future__ import annotations

from typing import Protocol

from .executor import Faults, GridWorld, Observation


class Driver(Protocol):
    def observe(self) -> Observation: ...
    def passable(self, cell: tuple[int, int]) -> bool: ...
    def execute(self, action: str, cell: tuple[int, int] | None = None) -> str: ...
    @property
    def pos(self) -> tuple[int, int]: ...
    @property
    def tick(self) -> int: ...


class MockGameDriver:
    """受控 mock 环境：网格世界 + 可选故障注入。"""

    def __init__(
        self,
        size: int = 20,
        start: tuple[int, int] = (1, 1),
        target: tuple[int, int] = (15, 15),
        walls: set[tuple[int, int]] | None = None,
        faults: Faults | None = None,
        seed: int = 0,
    ) -> None:
        self.world = GridWorld(
            size=size, start=start, target=target, walls=walls, faults=faults, seed=seed
        )

    # ---- Driver 接口 ----
    def observe(self) -> Observation:
        return self.world.observe()

    def passable(self, cell: tuple[int, int]) -> bool:
        return self.world.passable(cell)

    def execute(self, action: str, cell: tuple[int, int] | None = None) -> str:
        return self.world.execute(action, cell)

    @property
    def pos(self) -> tuple[int, int]:
        return self.world.pos

    @property
    def tick(self) -> int:
        return self.world.tick

    # ---- mock 专有 ----
    def describe(self) -> dict:
        obs = self.observe()
        return {
            "scene": "open_world",
            "driver": "mock",
            "pos": list(obs.pos),
            "target": list(obs.target),
            "tick": obs.tick,
            "walls": len(self.world.walls),
        }
