r"""为缺少证据帧的事件回填关键帧（不重跑 OCR）。

用法：
  python tools/backfill_evidence.py runs\p002_full.json data\videos\bili_p002_1080.mp4 data\frames\p002_full_backfill
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import video  # noqa: E402


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: backfill_evidence.py <project.json> <video> <frames_dir>")
        return 2
    project_path = Path(sys.argv[1])
    video_path = Path(sys.argv[2])
    frames_dir = Path(sys.argv[3])
    project = json.loads(project_path.read_text(encoding="utf-8"))

    missing: list[tuple[float, dict]] = []
    for event in project["events"]:
        if any(item.get("path") for item in event.get("evidence", [])):
            continue
        missing.append((float(event["video_time"]["start_s"]), event))

    if not missing:
        print(json.dumps({"missing": 0, "backfilled": 0}, ensure_ascii=False))
        return 0

    times = sorted({round(t, 2) for t, _ in missing})
    saved = video.extract_frames(video_path, times, frames_dir, prefix="ev")
    path_by_t = {}
    for path in saved:
        stem = path.stem.replace("ev_", "")
        try:
            path_by_t[round(float(stem), 2)] = str(path)
        except ValueError:
            continue

    filled = 0
    for t_s, event in missing:
        path = path_by_t.get(round(t_s, 2))
        if not path:
            nearest = min(path_by_t, key=lambda k: abs(k - t_s)) if path_by_t else None
            path = path_by_t.get(nearest) if nearest is not None else None
        if not path:
            continue
        event["evidence"].append(
            {
                "kind": "frame",
                "t_s": round(t_s, 2),
                "path": path,
                "bbox": None,
                "text": "",
                "note": "证据帧回填",
            }
        )
        filled += 1

    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"missing": len(missing), "backfilled": filled}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
