"""导出沙盘用证据数据：事件 + 证据帧副本。

用法：python tools/export_evidence.py runs\p002_full_v7.json --out sandbox/data
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--out", default="sandbox/data")
    parser.add_argument("--max-events", type=int, default=0, help="0 表示全部")
    args = parser.parse_args()
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    out_dir = ROOT / args.out
    frames_dir = out_dir / "evidence_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    events = project.get("events", [])
    if args.max_events:
        events = events[: args.max_events]
    duration = 0.0
    for segment in project.get("segments", []):
        duration = max(duration, float(segment.get("end_s", 0)))
    rows = []
    copied = 0
    for index, event in enumerate(events):
        params = event.get("action", {}).get("params", {})
        frame_rel = None
        for item in event.get("evidence", []):
            path = item.get("path")
            if not path:
                continue
            source = Path(path)
            if not source.is_absolute():
                source = ROOT / source
            if source.exists():
                target = frames_dir / f"evt_{index + 1:04d}{source.suffix.lower()}"
                shutil.copyfile(source, target)
                frame_rel = f"evidence_frames/{target.name}"
                copied += 1
                break
        rows.append(
            {
                "i": index + 1,
                "t": round(float(event.get("video_time", {}).get("start_s", 0)), 2),
                "type": event.get("action", {}).get("type", ""),
                "speaker": params.get("speaker", ""),
                "text": params.get("text") or params.get("quest_text") or "",
                "conf": event.get("confidence", 0),
                "frame": frame_rel,
            }
        )
    payload = {
        "project": project.get("project", {}).get("name", ""),
        "duration_s": round(duration, 2),
        "events": rows,
    }
    (out_dir / "evidence.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"events": len(rows), "frames": copied, "out": str(out_dir / "evidence.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
