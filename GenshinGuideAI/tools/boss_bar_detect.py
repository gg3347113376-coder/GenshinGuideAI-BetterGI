"""Boss 战检测（左端盖模板 + 时序连续性）→ 战斗窗口。

用法：
  python tools/boss_bar_detect.py --video data\videos\bili_boss_1080.mp4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import video  # noqa: E402
from ggai.combat import BossCapDetector, filter_sequence, windows_from_hits  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--min-consecutive", type=int, default=3)
    parser.add_argument("--out", default="runs/boss_bar.json")
    args = parser.parse_args()

    detector = BossCapDetector(threshold=args.threshold)
    samples = []
    for t, frame in video.iter_sampled_frames(args.video, sample_fps=args.fps):
        score = detector.score(frame)
        samples.append({"t": round(t, 2), "score": round(score, 3), "hit": score >= args.threshold})
    kept = filter_sequence(samples, min_consecutive=args.min_consecutive)
    windows = windows_from_hits(kept)
    raw_hits = sum(1 for s in samples if s["hit"])
    result = {
        "video": args.video,
        "threshold": args.threshold,
        "samples": len(samples),
        "raw_hits": raw_hits,
        "kept_hits": len(kept),
        "windows": windows,
        "hit_ratio_raw": round(raw_hits / len(samples), 3) if samples else 0,
        "samples_detail": samples,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("samples", "raw_hits", "kept_hits", "windows")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
