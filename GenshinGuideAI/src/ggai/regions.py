"""游戏 HUD 区域定义（按 0-1 相对坐标，自动适配分辨率）。"""
from __future__ import annotations

from typing import Iterable

import numpy as np

# name: (x, y, w, h) 相对比例，基于 1920x1080 的观察值
REGIONS: dict[str, tuple[float, float, float, float]] = {
    "minimap": (0.00, 0.00, 0.17, 0.30),
    "quest_tracker": (0.00, 0.13, 0.28, 0.18),
    "subtitle": (0.15, 0.75, 0.70, 0.16),
    "choices": (0.25, 0.30, 0.50, 0.45),
    "party": (0.78, 0.28, 0.22, 0.55),
    "hp": (0.30, 0.88, 0.40, 0.08),
    "uid": (0.80, 0.95, 0.20, 0.05),
}


def region_pixels(name: str, width: int, height: int) -> tuple[int, int, int, int]:
    x, y, w, h = REGIONS[name]
    x0 = max(0, int(round(x * width)))
    y0 = max(0, int(round(y * height)))
    x1 = min(width, int(round((x + w) * width)))
    y1 = min(height, int(round((y + h) * height)))
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def crop(image: np.ndarray, name: str) -> np.ndarray:
    height, width = image.shape[:2]
    x, y, w, h = region_pixels(name, width, height)
    return image[y:y + h, x:x + w]


def crop_many(image: np.ndarray, names: Iterable[str]) -> dict[str, np.ndarray]:
    return {name: crop(image, name) for name in names}
