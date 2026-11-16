"""把位置轨迹写入项目 JSON（move 事件 + position.map + 证据帧）。

用法：
  python tools/attach_positions.py --project runs\explore_project.json \
      --track runs\explore_track.json --out runs\explore_with_pos.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    track = json.loads(Path(args.track).read_text(encoding="utf-8"))
    source_id = (project.get("sources") or [{}])[0].get("id", "src_1")
    events = project.get("events", [])
    added = 0
    for sample in track.get("track", []):
        if not sample.get("ok") or not sample.get("world"):
            continue
        t = float(sample["t"])
        events.append(
            {
                "id": f"evt_move_{added:04d}",
                "source_id": source_id,
                "segment_id": None,
                "order": 0,
                "video_time": {"start_s": t, "end_s": t, "precision": "second"},
                "game_time": None,
                "sim_time": None,
                "actor": {"kind": "player", "name": "", "confidence": 0.8},
                "action": {
                    "type": "move",
                    "params": {"method": "minimap_sift", "interval_s": track.get("interval_s")},
                    "method": "inferred",
                    "notes": "小地图 SIFT 定位" + ("（插值）" if sample.get("interpolated") else ""),
                },
                "position": {
                    "map": {
                        "x": sample["world"][0],
                        "y": sample["world"][1],
                        "layer": "surface",
                        "region": "",
                        "anchor": "",
                        "error_m": None,
                        "method": "minimap",
                        "confidence": sample.get("confidence", 0.6),
                    },
                    "world": {
                        "x": None,
                        "y": None,
                        "z": None,
                        "error_m": None,
                        "method": "unknown",
                        "confidence": 0.0,
                    },
                },
                "preconditions": [],
                "expected_result": {"text": "位置采样", "checks": []},
                "observed_result": {
                    "text": f"map=({sample['world'][0]}, {sample['world'][1]})",
                    "checks": [],
                },
                "state_status": "observed" if not sample.get("interpolated") else "inferred",
                "confidence": sample.get("confidence", 0.6),
                "evidence": [
                    {
                        "kind": "frame",
                        "t_s": t,
                        "path": sample.get("frame", ""),
                        "bbox": None,
                        "text": "",
                        "note": "定位采样帧",
                    }
                ],
                "review": {"status": "pending"},
                "notes": "",
            }
        )
        added += 1

    events.sort(key=lambda event: float(event["video_time"]["start_s"]))
    for index, event in enumerate(events):
        event["order"] = index
    project["events"] = events
    errors = protocol.validate(project)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:5]}, ensure_ascii=False))
        return 1
    Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    positioned = sum(1 for e in events if e["position"]["map"]["x"] is not None)
    print(
        json.dumps(
            {"ok": True, "events": len(events), "positioned": positioned, "out": args.out},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
