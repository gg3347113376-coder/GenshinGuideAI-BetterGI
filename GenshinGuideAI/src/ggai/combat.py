"""战斗检测：Boss 血条左端盖模板匹配（等级无关）。

模板：assets/templates/boss_cap.png（血条左端箭头盖，取自 1080p 实拍）
判断：顶部区域 ±5% 多尺度匹配分数 >= 阈值；再按时序连续性过滤。
只覆盖「顶部 Boss 血条」，普通敌人/伤害数字不在此模块。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "data" / "templates" / "boss_cap.png"
BAND = (450, 40, 1450, 200)  # x0, y0, x1, y1（1920×1080 基准，按比例缩放）
SCALES = (0.95, 1.0, 1.05)
THRESHOLD = 0.55


class BossCapDetector:
    def __init__(self, template_path: str | Path | None = None, threshold: float = THRESHOLD) -> None:
        path = Path(template_path) if template_path else TEMPLATE_PATH
        self.template = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if self.template is None:
            raise FileNotFoundError(f"缺少模板：{path}")
        self.threshold = threshold

    def _band(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = BAND
        return frame[int(y0 / 1080 * h) : int(y1 / 1080 * h), int(x0 / 1920 * w) : int(x1 / 1920 * w)]

    def score(self, frame: np.ndarray) -> float:
        band = self._band(frame)
        best = 0.0
        for scale in SCALES:
            template = self.template
            if scale != 1.0:
                template = cv2.resize(self.template, None, fx=scale, fy=scale)
            if template.shape[0] > band.shape[0] or template.shape[1] > band.shape[1]:
                continue
            result = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
            best = max(best, float(result.max()))
        return best

    def hit(self, frame: np.ndarray) -> tuple[bool, float]:
        score = self.score(frame)
        return score >= self.threshold, score


def filter_sequence(samples: list[dict], min_consecutive: int = 3) -> list[dict]:
    kept: list[dict] = []
    streak: list[dict] = []
    for sample in samples:
        if sample.get("hit"):
            streak.append(sample)
        else:
            if len(streak) >= min_consecutive:
                kept.extend(streak)
            streak = []
    if len(streak) >= min_consecutive:
        kept.extend(streak)
    return kept


def windows_from_hits(samples: list[dict], gap_s: float = 8.0) -> list[list[float]]:
    hits = [s["t"] for s in samples if s.get("hit")]
    if not hits:
        return []
    windows = []
    start = prev = hits[0]
    for t in hits[1:]:
        if t - prev > gap_s:
            windows.append([round(start, 1), round(prev, 1)])
            start = t
        prev = t
    windows.append([round(start, 1), round(prev, 1)])
    return windows
