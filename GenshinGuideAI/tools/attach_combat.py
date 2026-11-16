"""把战斗窗口写入项目 JSON（fight_start / fight_end + 证据帧）。

用法：
  python tools/attach_combat.py --project runs\boss_project.json --windows runs\cap_boss.json \
      --video data\videos\bili_boss_1080.mp4 --out runs\boss_with_combat.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol, video  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--windows", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    detection = json.loads(Path(args.windows).read_text(encoding="utf-8"))
    windows = detection.get("windows", [])
    if not windows:
        print(json.dumps({"ok": True, "windows": 0, "events_added": 0}, ensure_ascii=False))
        return 0

    times = sorted({t for w in windows for t in w})
    frames_dir = ROOT / "data" / "frames" / (Path(args.video).stem + "_combat")
    saved = video.extract_frames(args.video, times, frames_dir, prefix="combat")
    frame_by_t: dict[float, str] = {}
    for path in saved:
        try:
            frame_by_t[round(float(path.stem.split("_")[-1]), 2)] = str(path)
        except ValueError:
            continue

    events = project.get("events", [])
    added = 0
    for start, end in windows:
        for kind, when, note in (("fight_start", start, "Boss 战开始"), ("fight_end", end, "Boss 战结束")):
            events.append(
                {
                    "id": f"evt_{kind}_{added:03d}",
                    "source_id": project.get("sources", [{}])[0].get("id", "src_1"),
                    "segment_id": None,
                    "order": 0,
                    "video_time": {"start_s": float(when), "end_s": float(when), "precision": "second"},
                    "game_time": None,
                    "sim_time": None,
                    "actor": {"kind": "player", "name": "", "confidence": 0.5},
                    "action": {
                        "type": kind,
                        "params": {"method": "boss_cap_template", "threshold": detection.get("threshold")},
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
                    "observed_result": {"text": "Boss 血条出现" if kind == "fight_start" else "Boss 血条消失", "checks": []},
                    "state_status": "inferred",
                    "confidence": 0.75,
                    "evidence": [
                        {
                            "kind": "frame",
                            "t_s": float(when),
                            "path": frame_by_t.get(round(float(when), 2), ""),
                            "bbox": None,
                            "text": "",
                            "note": "Boss 战窗口证据帧",
                        }
                    ],
                    "review": {"status": "pending"},
                    "notes": "基于顶部 Boss 血条左端盖模板检测",
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
    print(json.dumps({"ok": True, "windows": len(windows), "events_added": added, "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
