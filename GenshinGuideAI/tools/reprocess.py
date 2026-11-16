"""仅重跑事件抽取（复用已落盘的观测），不重新解码/OCR。

用法：
  python tools/reprocess.py runs\p002_full.obs.jsonl --source-sha <sha> --duration 1641.4 --out runs\p002_full_v2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402
from ggai.extract import Observation, extract_events  # noqa: E402
from ggai.ocr import OcrItem  # noqa: E402
from ggai.segmentation import classify_segments, coverage  # noqa: E402


def load_observations(path: Path) -> list[Observation]:
    observations = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        regions = {}
        for name, items in row.get("regions", {}).items():
            regions[name] = [
                OcrItem(text=i["text"], box=tuple(i["box"]), score=float(i["score"])) for i in items
            ]
        observations.append(Observation(t_s=row["t"], regions=regions, frame_path=row.get("frame")))
    return observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations")
    parser.add_argument("--out", required=True)
    parser.add_argument("--video", default="")
    parser.add_argument("--sha", default=None)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--id", default="proj_reprocess")
    parser.add_argument("--name", default="重跑抽取")
    args = parser.parse_args()

    observations = load_observations(Path(args.observations))
    project = protocol.new_project(args.id, args.name)
    project["project"]["model_versions"] = {"rules": "ggai-0.2.0", "mode": "reprocess"}
    protocol.add_source(
        project,
        "src_1",
        args.video or "unknown",
        args.duration or (observations[-1].t_s if observations else 0.0),
        sha256=args.sha,
    )
    segments = classify_segments(observations, total_end_s=args.duration or None)
    project["segments"] = segments
    events = extract_events(project, "src_1", observations)
    for event in events:
        t = event["video_time"]["start_s"]
        for seg in segments:
            if seg["start_s"] - 0.5 <= t <= seg["end_s"] + 0.5:
                event["segment_id"] = seg["id"]
                break
    errors = protocol.validate(project)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:5]}, ensure_ascii=False))
        return 1
    protocol.dump_project(project, args.out)
    print(json.dumps({"ok": True, "events": len(events), "coverage": coverage(segments)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
