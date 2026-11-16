"""用 VLM 复核关键帧场景分类，并与事件类型对照。

用法：python tools/vlm_check.py --project runs\p002_full_v7.json --samples 12
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.vlm import OllamaVLM, classify_scene  # noqa: E402


def expected_for(event: dict) -> str:
    action = event.get("action", {}).get("type", "")
    if action == "dialogue":
        return "dialogue"
    if action == "move":
        return "travel"
    if action.startswith("fight"):
        return "combat"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--out", default="runs/vlm_check.json")
    parser.add_argument("--model", default="qwen3-vl:4b")
    args = parser.parse_args()

    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    vlm = OllamaVLM(model=args.model)
    ok, message = vlm.available()
    if not ok:
        print(json.dumps({"ok": False, "message": message}, ensure_ascii=False))
        return 1

    candidates = []
    for event in project.get("events", []):
        frame = next((v.get("path") for v in event.get("evidence", []) if v.get("path")), None)
        if not frame:
            continue
        path = Path(frame)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            continue
        candidates.append((event, path))
    if not candidates:
        print(json.dumps({"ok": False, "message": "没有可用证据帧"}, ensure_ascii=False))
        return 1

    step = max(1, len(candidates) // args.samples)
    picked = candidates[::step][: args.samples]
    rows = []
    correct = 0
    for event, path in picked:
        result = classify_scene(vlm, path)
        expected = expected_for(event)
        hit = result["scene"] == expected
        correct += 1 if hit else 0
        rows.append(
            {
                "t": event.get("video_time", {}).get("start_s"),
                "event_type": event.get("action", {}).get("type"),
                "expected": expected,
                "predicted": result["scene"],
                "confidence": result["confidence"],
                "reason": result["reason"],
                "hit": hit,
                "frame": str(path),
            }
        )
    summary = {
        "ok": True,
        "model": args.model,
        "samples": len(rows),
        "accuracy": round(correct / len(rows), 3) if rows else 0.0,
        "rows": rows,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("ok", "model", "samples", "accuracy")}, ensure_ascii=False))
    for row in rows:
        print(f"  t={row['t']:>7} event={row['event_type']:<10} expected={row['expected']:<9} predicted={row['predicted']:<9} hit={row['hit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
