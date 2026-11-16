"""构建位置轨迹：对视频按间隔做 SIFT 小地图定位，失败点插值。

用法：
  python tools/build_position_track.py --video data\videos\bili_explore_1080.mp4 \
      --start 0 --end 555 --step 5 --out runs\explore_track.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cv2  # noqa: E402

from ggai import video  # noqa: E402
from sift_localize import load_features, localize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=0.0)
    parser.add_argument("--step", type=float, default=5.0)
    parser.add_argument("--center", default="205,160")
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--out", default="runs/position_track.json")
    args = parser.parse_args()

    info = video.probe(args.video)
    end = args.end or info.duration_s
    times = []
    t = args.start
    while t < end:
        times.append(round(t, 2))
        t += args.step

    cx, cy = (int(v) for v in args.center.split(","))
    frames_dir = ROOT / "data" / "frames" / (Path(args.video).stem + "_pos")
    saved = video.extract_frames(args.video, times, frames_dir, prefix="pos")
    frame_by_time = {}
    for path in saved:
        try:
            frame_by_time[round(float(path.stem.split("_")[-1]), 2)] = str(path)
        except ValueError:
            continue

    keypoints, descriptors = load_features()
    matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=50))
    sift = cv2.SIFT_create()
    prev = None
    samples = []
    for t in times:
        path = frame_by_time.get(t)
        if not path:
            samples.append({"t": t, "ok": False, "reason": "frame missing"})
            continue
        frame = cv2.imread(path)
        result = localize(frame, (cx, cy), args.size, keypoints, descriptors, matcher, sift, args.scale, prev)
        result["t"] = t
        result["frame"] = path
        if result.get("ok"):
            prev = tuple(result["map_px"])
            matches = result.get("matches", 0)
            spread = result.get("spread_px", 500)
            result["confidence"] = round(min(0.95, 0.5 + matches / 200.0) * max(0.5, 1.0 - spread / 900.0), 3)
        samples.append(result)

    # 线性插值：成功点之间、间隔不超过 3 步的空洞
    for index, sample in enumerate(samples):
        if sample.get("ok"):
            continue
        left = next((samples[i] for i in range(index - 1, -1, -1) if samples[i].get("ok")), None)
        right = next((samples[i] for i in range(index + 1, len(samples)) if samples[i].get("ok")), None)
        if not left or not right:
            continue
        span = (right["t"] - left["t"]) / args.step
        if span > 3.0:
            continue
        ratio = (sample["t"] - left["t"]) / (right["t"] - left["t"])
        sample["ok"] = True
        sample["interpolated"] = True
        sample["world"] = [
            round(left["world"][0] + (right["world"][0] - left["world"][0]) * ratio, 1),
            round(left["world"][1] + (right["world"][1] - left["world"][1]) * ratio, 1),
        ]
        sample["confidence"] = 0.4
        sample["reason"] = "interpolated"

    ok = [s for s in samples if s.get("ok")]
    out = {
        "video": args.video,
        "interval_s": args.step,
        "samples": len(samples),
        "ok": len(ok),
        "interpolated": sum(1 for s in ok if s.get("interpolated")),
        "coverage": round(len(ok) / len(samples), 3) if samples else 0,
        "track": samples,
    }
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("samples", "ok", "interpolated", "coverage")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
