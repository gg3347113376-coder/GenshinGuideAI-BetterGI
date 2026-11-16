"""过滤 UP 主叠加字幕：底部字幕区黄色像素占比过高的事件。

用法：python tools/filter_captions.py --project runs\explore_with_pos_v2.json --out runs\explore_clean.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402


def yellow_ratio(path: str) -> float:
    image = cv2.imread(path)
    if image is None:
        return 0.0
    h, w = image.shape[:2]
    crop = image[int(0.70 * h) : int(0.92 * h), int(0.18 * w) : int(0.82 * w)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (15, 120, 140), (40, 255, 255))
    return float(yellow.mean()) / 255.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=float, default=0.03)
    parser.add_argument("--drop-dialogue", action="store_true", help="整段删除对话事件（用于无对白素材）")
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    kept, removed = [], []
    for event in project.get("events", []):
        if event.get("action", {}).get("type") != "dialogue":
            kept.append(event)
            continue
        frame = next((v.get("path") for v in event.get("evidence", []) if v.get("path")), None)
        ratio = yellow_ratio(frame) if frame else 0.0
        if args.drop_dialogue or ratio > args.threshold:
            removed.append(
                {
                    "t": event["video_time"]["start_s"],
                    "text": event["action"]["params"].get("text", "")[:40],
                    "yellow_ratio": round(ratio, 3),
                }
            )
            continue
        kept.append(event)

    for index, event in enumerate(kept):
        event["order"] = index
    project["events"] = kept
    errors = protocol.validate(project)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:5]}, ensure_ascii=False))
        return 1
    Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "runs" / "captions_removed.json").write_text(
        json.dumps(removed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"ok": True, "kept": len(kept), "removed": len(removed), "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
