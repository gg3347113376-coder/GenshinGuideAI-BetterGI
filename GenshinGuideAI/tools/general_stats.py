"""对比多个项目的结构指标（用于泛化测试，无需金标准）。

用法：python tools/general_stats.py runs\p002_full_v7.json runs\p001_full.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402
from ggai.segmentation import coverage as seg_coverage  # noqa: E402


def stats(path: Path) -> dict:
    project = json.loads(path.read_text(encoding="utf-8"))
    events = project.get("events", [])
    dialogues = [e for e in events if e.get("action", {}).get("type") == "dialogue"]
    moves = [e for e in events if e.get("action", {}).get("type") == "move"]
    with_speaker = sum(1 for e in dialogues if e.get("action", {}).get("params", {}).get("speaker"))
    lengths = [len(e.get("action", {}).get("params", {}).get("text", "")) for e in dialogues]
    duration = sum(float(s.get("end_s", 0)) - float(s.get("start_s", 0)) for s in project.get("segments", []))
    summary = protocol.summarise(project)
    seg = seg_coverage(project.get("segments", []))
    return {
        "file": path.name,
        "events": len(events),
        "events_per_min": round(len(events) / (duration / 60), 2) if duration else 0,
        "dialogue": len(dialogues),
        "move": len(moves),
        "dialogue_speaker_rate": round(with_speaker / len(dialogues), 3) if dialogues else 0,
        "dialogue_len_median": statistics.median(lengths) if lengths else 0,
        "segments": summary["segments"],
        "dialogue_ratio": seg["dialogue_ratio"],
        "mean_confidence": summary["mean_confidence"],
        "evidence_ratio": summary["events"] and round(
            sum(1 for e in events if any(v.get("path") for v in e.get("evidence", []))) / len(events), 3
        ),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: general_stats.py <project.json> [...]")
        return 2
    rows = [stats(Path(p)) for p in sys.argv[1:]]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
