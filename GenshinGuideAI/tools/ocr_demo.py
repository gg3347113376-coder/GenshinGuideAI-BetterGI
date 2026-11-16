"""对单张图片按 HUD 区域做 OCR，用于验证识别效果。

用法：
  python tools/ocr_demo.py <image> [--regions quest_tracker,subtitle] [--full]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import regions  # noqa: E402
from ggai.ocr import make_ocr  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--regions", default="", help="逗号分隔；留空表示全部预定义区域")
    parser.add_argument("--full", action="store_true", help="额外做整图 OCR")
    parser.add_argument("--backend", default="rapidocr")
    args = parser.parse_args()

    import cv2
    import numpy as np

    data = cv2.imdecode(np.fromfile(args.image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if data is None:
        print(json.dumps({"error": "无法读取图片"}, ensure_ascii=False))
        return 1
    ocr = make_ocr(args.backend)
    names = [n.strip() for n in args.regions.split(",") if n.strip()] or list(regions.REGIONS)
    out = {"image": args.image, "size": [data.shape[1], data.shape[0]], "regions": {}}
    for name in names:
        crop = regions.crop(data, name)
        if crop.size == 0:
            out["regions"][name] = []
            continue
        items = ocr.recognize(crop)
        out["regions"][name] = [
            {"text": i.text, "box": list(i.box), "score": round(i.score, 3)} for i in items
        ]
    if args.full:
        items = ocr.recognize(data)
        out["full"] = [{"text": i.text, "box": list(i.box), "score": round(i.score, 3)} for i in items]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
