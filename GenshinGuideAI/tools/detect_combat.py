"""基于队伍血条变化的战斗检测（启发式，输出 fight_start / fight_end）。

用法：
  python tools/detect_combat.py --video data\videos\bili_p002_1080.mp4 ^
      --project runs\p002_full_v7.json --out runs\p002_combat.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import video  # noqa: E402
from ggai.ocr import make_ocr  # noqa: E402

HP_REGION = (0.46, 0.900, 0.075, 0.050)  # x, y, w, h（相对坐标，只保留血量数字）
HP_PATTERN = re.compile(r"(\d{2,6})\s*/\s*(\d{2,6})")


def crop_hp(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    x, y, bw, bh = HP_REGION
    return frame[int(y * h) : int((y + bh) * h), int(x * w) : int((x + bw) * w)]


def has_green_bar(frame: np.ndarray) -> bool:
    h, w = frame.shape[:2]
    x, y, bw, bh = (0.36, 0.900, 0.26, 0.030)
    bar = frame[int(y * h) : int((y + bh) * h), int(x * w) : int((x + bw) * w)]
    if bar.size == 0:
        return False
    hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
    return float(mask.mean()) / 255.0 > 0.15


def parse_hp(engine, crop: np.ndarray) -> tuple[int, int] | None:
    if crop.size == 0:
        return None
    enlarged = cv2.resize(crop, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    raw, _ = engine(enlarged, use_det=False, use_cls=False, use_rec=True)
    texts = [row[0] for row in (raw or []) if isinstance(row, (list, tuple)) and len(row) >= 2 and row[1] > 0.3]
    for text in texts:
        match = HP_PATTERN.search(text.replace(" ", ""))
        if match:
            return int(match.group(1)), int(match.group(2))
    joined = "".join(texts).replace(" ", "")
    digits = re.sub(r"\D", "", joined)
    if len(digits) >= 8 and len(digits) % 2 == 0:
        half = len(digits) // 2
        return int(digits[:half]), int(digits[half:])
    match = HP_PATTERN.search(joined)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def windows_from_drops(samples: list[tuple[float, int, int]], drop_ratio: float = 0.004) -> list[tuple[float, float]]:
    """掉血点 → 合并成战斗窗口。"""
    drops: list[float] = []
    last: tuple[int, int] | None = None
    for t, hp, hp_max in samples:
        if hp_max <= 0:
            continue
        if last is not None:
            prev_hp, prev_max = last
            if prev_max == hp_max and hp < prev_hp and (prev_hp - hp) / prev_max >= drop_ratio:
                drops.append(t)
        last = (hp, hp_max)
    if len(drops) < 2:
        return []
    spans = [[max(0.0, t - 8.0), t + 12.0] for t in drops]
    merged: list[list[float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(a, 1), round(b, 1)) for a, b in merged]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--max-seconds", type=float, default=0.0)
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    ocr = make_ocr("rapidocr")
    engine = ocr.raw_engine()
    samples: list[tuple[float, int, int]] = []
    for index, (t, frame) in enumerate(video.iter_sampled_frames(
        args.video, sample_fps=args.fps, end_s=args.max_seconds or None
    )):
        if index % 300 == 0:
            print(f"  sample {index} t={t:.1f} saved={len(samples)}", flush=True)
        crop = crop_hp(frame)
        parsed = parse_hp(engine, crop)
        if parsed:
            samples.append((t, parsed[0], parsed[1]))
    raw_windows = windows_from_drops(samples)
    windows = []
    for start, end in raw_windows:
        density = sum(1 for t, _, _ in samples if start <= t <= end)
        if density >= 5:
            windows.append((start, end))

    # 提取窗口起止证据帧
    times = sorted({w[0] for w in windows} | {w[1] for w in windows})
    frames_dir = ROOT / "data" / "frames" / (Path(args.video).stem + "_combat")
    saved = video.extract_frames(args.video, times, frames_dir, prefix="combat") if times else []
    frame_by_t: dict[float, str] = {}
    for path in saved:
        try:
            frame_by_t[round(float(path.stem.split("_")[-1]), 2)] = str(path)
        except ValueError:
            continue

    events = project.get("events", [])
    added = 0
    for start, end in windows:
        for kind, when, note in (("fight_start", start, "战斗开始（掉血）"), ("fight_end", end, "战斗结束（窗口）")):
            events.append(
                {
                    "id": f"evt_combat_{added + 1:04d}",
                    "source_id": project.get("sources", [{}])[0].get("id", "src_1"),
                    "segment_id": None,
                    "order": 0,
                    "video_time": {"start_s": when, "end_s": when, "precision": "second"},
                    "game_time": None,
                    "sim_time": None,
                    "actor": {"kind": "player", "name": "", "confidence": 0.5},
                    "action": {
                        "type": kind,
                        "params": {"method": "hp_drop_heuristic"},
                        "method": "inferred",
                        "notes": note,
                    },
                    "position": {
                        "map": {"x": None, "y": None, "layer": "unknown", "region": "", "anchor": "",
                                "error_m": None, "method": "unknown", "confidence": 0.0},
                        "world": {"x": None, "y": None, "z": None, "error_m": None,
                                  "method": "unknown", "confidence": 0.0},
                    },
                    "preconditions": [],
                    "expected_result": {"text": note, "checks": []},
                    "observed_result": {"text": "血条变化", "checks": []},
                    "state_status": "inferred",
                    "confidence": 0.45,
                    "evidence": [
                        {
                            "kind": "frame",
                            "t_s": when,
                            "path": frame_by_t.get(round(when, 2), ""),
                            "bbox": None,
                            "text": "",
                            "note": "战斗窗口证据帧",
                        }
                    ],
                    "review": {"status": "pending"},
                    "notes": "基于队伍血条掉血的启发式检测，需人工复核",
                }
            )
            added += 1
    events.sort(key=lambda e: float(e["video_time"]["start_s"]))
    for index, event in enumerate(events):
        event["order"] = index
    project["events"] = events
    Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "samples": len(samples),
                "windows": len(windows),
                "events_added": added,
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
