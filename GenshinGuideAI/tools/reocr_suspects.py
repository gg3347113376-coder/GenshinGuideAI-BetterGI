"""对证据帧做 2 倍放大重识别，替换更优文本/说话人，并输出变化统计。

用法：python tools/reocr_suspects.py --project runs\p002_full_v7.json --out runs\p002_reocr.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.extract import _valid_speaker, norm_text, plausible_text, similar  # noqa: E402
from ggai.metrics import text_similarity  # noqa: E402
from ggai.ocr import make_ocr  # noqa: E402
from ggai.strips import SUB_BANDS, SPEAKER_BANDS  # noqa: E402

SCALE = 2.0


def crop(img: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    h, w = img.shape[:2]
    x, y, bw, bh = box
    return img[int(y * h) : int((y + bh) * h), int(x * w) : int((x + bw) * w)]


def ocr_lines(engine, img: np.ndarray, bands: list[tuple[float, float, float, float]], min_score: float) -> list[tuple[str, float]]:
    results: list[tuple[str, float]] = []
    for band in bands:
        piece = crop(img, band)
        if piece.size == 0:
            continue
        enlarged = cv2.resize(piece, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
        raw, _ = engine(enlarged, use_det=False, use_cls=False, use_rec=True)
        for row in raw or []:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                text = norm_text(str(row[0]))
                score = float(row[1])
                if score >= min_score and plausible_text(text, min_cjk=2, max_len=60):
                    results.append((text, score))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--conservative", action="store_true")
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    ocr = make_ocr("rapidocr")
    engine = ocr.raw_engine()
    changed_text = changed_speaker = checked = 0
    events = project.get("events", [])
    if args.limit:
        events = events[: args.limit]
    for event in events:
        if event.get("action", {}).get("type") != "dialogue":
            continue
        frame_path = next((v.get("path") for v in event.get("evidence", []) if v.get("path")), None)
        if not frame_path:
            continue
        path = Path(frame_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            continue
        img = cv2.imread(str(path))
        if img is None:
            continue
        checked += 1
        lines = ocr_lines(engine, img, SUB_BANDS, min_score=0.5)
        if lines:
            lines.sort(key=lambda item: (item[1] * min(len(item[0]), 40)), reverse=True)
            new_text = lines[0][0]
            old_text = event["action"]["params"].get("text", "")
            if new_text and text_similarity(new_text, old_text) < 0.999:
                allow = True
                if args.conservative:
                    allow = len(old_text) < 6 and len(new_text) > len(old_text)
                if allow and (text_similarity(new_text, old_text) < 0.9 or len(new_text) > len(old_text)):
                    event["action"]["params"]["text"] = new_text
                    event.setdefault("observed_result", {})["text"] = new_text
                    changed_text += 1
        speaker_lines = ocr_lines(engine, img, SPEAKER_BANDS, min_score=0.45)
        valid = [(norm_text(t), s) for t, s in speaker_lines if _valid_speaker(norm_text(t))]
        if valid:
            new_speaker = max(valid, key=lambda item: item[1])[0]
            old_speaker = event["action"]["params"].get("speaker", "")
            allow_speaker = True
            if args.conservative:
                allow_speaker = old_speaker == ""
            if allow_speaker and new_speaker and new_speaker != old_speaker and similar(new_speaker, old_speaker) < 0.95:
                event["action"]["params"]["speaker"] = new_speaker
                event.setdefault("actor", {})["name"] = new_speaker
                changed_speaker += 1
    Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checked": checked, "text_changed": changed_text, "speaker_changed": changed_speaker, "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
