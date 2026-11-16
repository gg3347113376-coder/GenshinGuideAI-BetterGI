"""OCR 适配层：RapidOCR（离线 ONNX）优先，Umi-OCR HTTP 作为可选后端。"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class OcrItem:
    text: str
    box: tuple[int, int, int, int]  # x, y, w, h（相对输入图像）
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "box": list(self.box), "score": round(self.score, 4)}


def _load_image(image: str | Path | np.ndarray) -> np.ndarray:
    if isinstance(image, (str, Path)):
        data = cv2.imdecode(np.fromfile(str(image), dtype=np.uint8), cv2.IMREAD_COLOR)
        if data is None:
            raise ValueError(f"无法读取图片：{image}")
        return data
    return image


class RapidOcr:
    """RapidOCR 适配器；首次调用时加载模型。"""

    name = "rapidocr-onnxruntime"

    def __init__(self) -> None:
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def raw_engine(self):
        """暴露底层引擎，供 strips 快速模式直接调用（use_det=False）。"""
        return self._get_engine()

    def recognize(self, image: str | Path | np.ndarray) -> list[OcrItem]:
        img = _load_image(image)
        result, _elapse = self._get_engine()(img)
        items: list[OcrItem] = []
        for row in result or []:
            box, text, score = row[0], row[1], float(row[2])
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0, y0 = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x0), int(max(ys) - y0)
            items.append(OcrItem(text=str(text).strip(), box=(x0, y0, w, h), score=score))
        return items


class UmiOcr:
    """Umi-OCR HTTP API 适配器（需本机运行 Umi-OCR 并开启 HTTP 服务）。"""

    name = "umi-ocr-http"

    def __init__(self, endpoint: str = "http://127.0.0.1:1224/api/ocr") -> None:
        self.endpoint = endpoint

    def recognize(self, image: str | Path | np.ndarray) -> list[OcrItem]:
        img = _load_image(image)
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise ValueError("图片编码失败")
        import base64

        payload = json.dumps({"base64": base64.b64encode(buf.tobytes()).decode()}).encode()
        req = urllib.request.Request(
            self.endpoint, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        items = []
        for row in data.get("data", []):
            box = row.get("box", [0, 0, 0, 0])
            items.append(
                OcrItem(
                    text=str(row.get("text", "")).strip(),
                    box=(int(box[0]), int(box[1]), int(box[2] - box[0]), int(box[3] - box[1])),
                    score=float(row.get("score", 0)),
                )
            )
        return items


def make_ocr(backend: str = "rapidocr"):
    if backend == "rapidocr":
        return RapidOcr()
    if backend == "umi":
        return UmiOcr()
    raise ValueError(f"未知 OCR 后端：{backend}")
