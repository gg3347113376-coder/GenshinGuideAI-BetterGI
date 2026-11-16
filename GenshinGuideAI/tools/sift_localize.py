"""用 BetterGI 预计算 SIFT 特征定位小地图（旋转/尺度无关）。

- 关键点：Teyvat_0_2048_SIFT.kp.bin，681139×7 float32（x,y,...）
- 描述子：Teyvat_0_2048_SIFT.mat.png，681139×128 uint8
- 换算：gameX=(32768-x)/2，gameY=(24576-y)/2（2048 级图像坐标）

用法：
  python tools/sift_localize.py --video data\videos\bili_explore_1080.mp4 --times 60,120,180
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = Path(r"C:\Program Files\BetterGI\Assets\Map\Teyvat")
KP_BIN = MAP_DIR / "Teyvat_0_2048_SIFT.kp.bin"
DESC_PNG = MAP_DIR / "Teyvat_0_2048_SIFT.mat.png"


def load_features() -> tuple[np.ndarray, np.ndarray]:
    keypoints = np.fromfile(str(KP_BIN), dtype=np.float32).reshape(-1, 7)
    descriptors = cv2.imread(str(DESC_PNG), cv2.IMREAD_UNCHANGED)
    if descriptors is None:
        raise FileNotFoundError(DESC_PNG)
    count = min(len(keypoints), len(descriptors))
    return keypoints[:count], descriptors[:count].astype(np.float32)


def image_to_game(x: float, y: float) -> tuple[float, float]:
    return (32768.0 - x) / 2.0, (24576.0 - y) / 2.0


def localize(frame: np.ndarray, center: tuple[int, int], size: int, keypoints: np.ndarray, descriptors: np.ndarray, matcher, sift, scale: float, prev: tuple[float, float] | None = None) -> dict:
    cx, cy = center
    half = size // 2
    crop = frame[max(0, cy - half) : cy + half, max(0, cx - half) : cx + half]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    target = max(200, int(size * scale))
    gray = cv2.resize(gray, (target, target), interpolation=cv2.INTER_AREA)
    query_kp, query_desc = sift.detectAndCompute(gray, None)
    if query_desc is None or len(query_kp) < 10:
        return {"ok": False, "reason": "query keypoints too few", "count": 0 if query_desc is None else len(query_kp)}
    matches = matcher.knnMatch(query_desc, descriptors, k=2)
    good = []
    for pair in matches:
        if len(pair) < 2:
            continue
        first, second = pair
        if first.distance < 0.75 * second.distance:
            good.append(first)
    if len(good) < 6:
        return {"ok": False, "reason": "too few matches", "count": len(good)}
    xs = keypoints[[m.trainIdx for m in good], 0]
    ys = keypoints[[m.trainIdx for m in good], 1]
    if prev is not None:
        keep = np.hypot(xs - prev[0], ys - prev[1]) <= 1200
        if keep.sum() < 8:
            return {"ok": False, "reason": "no matches near previous position", "count": int(keep.sum())}
        xs, ys = xs[keep], ys[keep]
        good = [g for g, k in zip(good, keep) if k]
    # 用中位数抑制离群匹配
    mx, my = float(np.median(xs)), float(np.median(ys))
    spread = float(np.median(np.hypot(xs - mx, ys - my)))
    if spread > 450:
        return {"ok": False, "reason": "matches too scattered", "spread_px": round(spread, 1), "count": len(good)}
    gx, gy = image_to_game(mx, my)
    return {
        "ok": True,
        "matches": len(good),
        "spread_px": round(spread, 1),
        "map_px": [round(mx, 1), round(my, 1)],
        "world": [round(gx, 1), round(gy, 1)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--times", default="60,120,180")
    parser.add_argument("--center", default="205,160")
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--prev", default="")
    parser.add_argument("--no-roi", action="store_true")
    parser.add_argument("--out", default="runs/sift_localize.json")
    args = parser.parse_args()
    cx, cy = (int(v) for v in args.center.split(","))
    times = [float(t) for t in args.times.split(",")]
    from ggai import video

    out_dir = ROOT / "data" / "frames" / "sift_probe"
    saved = video.extract_frames(args.video, times, out_dir, prefix="sift")
    keypoints, descriptors = load_features()
    matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=50))
    sift = cv2.SIFT_create()
    prev = None
    if args.prev:
        prev = tuple(float(v) for v in args.prev.split(","))
    results = []
    for path in saved:
        frame = cv2.imread(str(path))
        result = localize(frame, (cx, cy), args.size, keypoints, descriptors, matcher, sift, args.scale, prev)
        result["t"] = path.stem.split("_")[-1]
        if result.get("ok") and not args.no_roi:
            prev = tuple(result["map_px"])
        results.append(result)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in results:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
