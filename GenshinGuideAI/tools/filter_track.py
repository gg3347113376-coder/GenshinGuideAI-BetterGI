"""轨迹质量过滤：标记速度异常点（疑似传送/匹配错误）。

用法：python tools/filter_track.py --track runs\explore_track.json --out runs\explore_track_v2.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-step", type=float, default=150.0, help="相邻采样最大合理位移（单位）")
    args = parser.parse_args()

    data = json.loads((ROOT / args.track).read_text(encoding="utf-8"))
    track = data.get("track", [])
    ok = [s for s in track if s.get("ok")]
    suspects = 0
    prev = None
    for sample in ok:
        if prev is not None:
            step = math.hypot(sample["world"][0] - prev["world"][0], sample["world"][1] - prev["world"][1])
            sample["step"] = round(step, 1)
            if step > args.max_step:
                sample["suspect"] = True
                sample["confidence"] = min(sample.get("confidence", 0.5), 0.3)
                suspects += 1
        prev = sample
    steps = [s.get("step") for s in ok if s.get("step") is not None]
    data["suspects"] = suspects
    data["step_stats"] = {
        "mean": round(sum(steps) / len(steps), 1) if steps else 0,
        "max": max(steps) if steps else 0,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"samples": len(track), "ok": len(ok), "suspects": suspects, "step_stats": data["step_stats"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
