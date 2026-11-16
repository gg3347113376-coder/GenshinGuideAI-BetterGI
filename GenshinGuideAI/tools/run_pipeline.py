"""方向一 MVP 命令行：视频 → 协议 JSON。

用法：
  python tools/run_pipeline.py --video data/videos/x.mp4 --start 0 --duration 300 ^
      --out runs/p002.json --frames data/frames/p002 --db runs/p002.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.pipeline import build_project  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--sample-fps", type=float, default=1.0)
    parser.add_argument("--frames", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--ocr", default="rapidocr")
    parser.add_argument("--ocr-mode", default="strips", choices=["strips", "regions"])
    parser.add_argument("--id", default="proj_auto")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    result = build_project(
        video_path=args.video,
        out_json=args.out,
        project_id=args.id,
        name=args.name,
        start_s=args.start,
        duration_s=args.duration,
        sample_fps=args.sample_fps,
        frames_dir=args.frames,
        ocr_backend=args.ocr,
        ocr_mode=args.ocr_mode,
        db_path=args.db,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
