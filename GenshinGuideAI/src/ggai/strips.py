"""快速 HUD 文本读取：固定条带 + 免检测 OCR（RapidOCR use_det=False）。

为什么不用整帧检测：PaddleOCR/RapidOCR 的检测模型在 CPU 上约 1.3–2.2 秒/帧，
而单行条带识别约 20–60 毫秒。攻略视频里真正需要的是任务追踪、说话人、字幕三类文本，
用固定条带覆盖即可，速度快一个数量级。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np

from .ocr import OcrItem

# 相对坐标 (x, y, w, h)，基于 1920x1080 实测
QUEST_STRIPS: dict[str, tuple[float, float, float, float]] = {
    "quest_title": (0.020, 0.190, 0.230, 0.032),
    "quest_sub": (0.020, 0.225, 0.230, 0.030),
    "quest_extra": (0.020, 0.255, 0.230, 0.030),
}

# 字幕/说话人会出现两种高度：开放世界对话约 y=0.74–0.82，过场约 y=0.80–0.88
SPEAKER_BANDS: list[tuple[float, float, float, float]] = [
    (0.30, 0.716, 0.40, 0.034),
    (0.30, 0.744, 0.40, 0.034),
    (0.30, 0.760, 0.40, 0.034),
    (0.30, 0.776, 0.40, 0.034),
    (0.30, 0.788, 0.40, 0.032),
    (0.30, 0.804, 0.40, 0.032),
]

SUB_BANDS: list[tuple[float, float, float, float]] = [
    (0.120, 0.684, 0.760, 0.038),
    (0.120, 0.720, 0.760, 0.038),
    (0.120, 0.750, 0.760, 0.038),
    (0.120, 0.780, 0.760, 0.038),
    (0.120, 0.810, 0.760, 0.038),
    (0.120, 0.840, 0.760, 0.038),
    (0.120, 0.870, 0.760, 0.038),
]


@dataclass
class StripHit:
    text: str
    score: float
    box: tuple[int, int, int, int]


def _interp(result) -> list[tuple[str, float]]:
    """兼容 use_det=False 的 [[text, score]] 返回格式。"""
    out: list[tuple[str, float]] = []
    if not result:
        return out
    for row in result:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            text, score = row[0], row[1]
            if isinstance(text, str) and text.strip():
                out.append((text.strip(), float(score)))
    return out


def _crop(image: np.ndarray, box: tuple[float, float, float, float]) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    h, w = image.shape[:2]
    x, y, bw, bh = box
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + bw) * w)), int(round((y + bh) * h))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    return image[y0:y1, x0:x1], (x0, y0, x1 - x0, y1 - y0)


def read_hud(image: np.ndarray, engine, min_score: float = 0.45) -> dict[str, list[OcrItem]]:
    """读取任务追踪、说话人与字幕，返回按区域分组的结果。"""
    result: dict[str, list[OcrItem]] = {"quest_tracker": [], "subtitle": [], "speaker": []}

    # 说话人条带：细体金字，多条窄带扫描 + 2 倍放大
    speaker_best: dict[str, OcrItem] = {}
    for band in SPEAKER_BANDS:
        speaker_crop, speaker_box = _crop(image, band)
        if speaker_crop.size == 0:
            continue
        enlarged = cv2.resize(speaker_crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        rows = _interp(engine(enlarged, use_det=False, use_cls=False, use_rec=True)[0])
        for text, score in rows:
            if score >= 0.40 and 2 <= len(text) <= 8:
                if text not in speaker_best or score > speaker_best[text].score:
                    speaker_best[text] = OcrItem(text=text, box=speaker_box, score=score)
    result["speaker"] = sorted(speaker_best.values(), key=lambda i: -i.score)[:3]

    for name, box in QUEST_STRIPS.items():
        crop, (x0, y0, cw, ch) = _crop(image, box)
        if crop.size == 0:
            continue
        rows = _interp(engine(crop, use_det=False, use_cls=False, use_rec=True)[0])
        for text, score in rows:
            if score >= min_score and len(text) >= 2:
                result["quest_tracker"].append(
                    OcrItem(text=text, box=(x0, y0, cw, ch), score=score)
                )

    # 字幕：多带覆盖，按文本去重，保留得分最高的一条
    best: dict[str, OcrItem] = {}
    for box in SUB_BANDS:
        crop, (x0, y0, cw, ch) = _crop(image, box)
        if crop.size == 0:
            continue
        rows = _interp(engine(crop, use_det=False, use_cls=False, use_rec=True)[0])
        for text, score in rows:
            if score < min_score or len(text) < 2:
                continue
            key = text.replace(" ", "")
            if key not in best or score > best[key].score:
                best[key] = OcrItem(text=text, box=(x0, y0, cw, ch), score=score)
    # 过短/重复噪声过滤
    result["subtitle"] = sorted(best.values(), key=lambda i: -i.score)[:3]
    return result
