"""合并两个项目 JSON（用于「坐标 + 战斗」端到端演示）。

用法：
  python tools/merge_projects.py --base runs\explore_with_pos.json --extra runs\boss_with_combat.json --out runs\combined_demo.json
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
    parser.add_argument("--base", required=True)
    parser.add_argument("--extra", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    extra = json.loads(Path(args.extra).read_text(encoding="utf-8"))

    base_sources = base.get("sources", [])
    existing_ids = {s.get("id") for s in base_sources}
    id_map: dict[str, str] = {}
    for source in extra.get("sources", []):
        old = source.get("id")
        new = old
        suffix = 1
        while new in existing_ids:
            suffix += 1
            new = f"{old}_2" if suffix == 2 else f"{old}_{suffix}"
        id_map[old] = new
        source["id"] = new
        base_sources.append(source)
        existing_ids.add(new)
    base["sources"] = base_sources

    base_events = base.get("events", [])
    for event in extra.get("events", []):
        event["source_id"] = id_map.get(event.get("source_id"), event.get("source_id"))
        base_events.append(event)
    base_events.sort(key=lambda e: (e.get("source_id", ""), float(e["video_time"]["start_s"])))
    for index, event in enumerate(base_events):
        event["order"] = index
    base["events"] = base_events

    errors = protocol.validate(base)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:5]}, ensure_ascii=False))
        return 1
    Path(args.out).write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    positioned = sum(1 for e in base_events if e["position"]["map"]["x"] is not None)
    fights = sum(1 for e in base_events if e["action"]["type"].startswith("fight"))
    print(
        json.dumps(
            {
                "ok": True,
                "sources": len(base_sources),
                "events": len(base_events),
                "positioned": positioned,
                "fight_events": fights,
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
