"""导出沙盘可执行的计划（示意坐标，供 Godot NavMesh 执行）。

用法：
  python tools/export_exec_plan.py --out sandbox/data/exec_plan.json
  python tools/export_exec_plan.py --bad --out sandbox/data/exec_plan_bad.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(nodes: list[tuple[float, float]]) -> dict:
    steps = []
    for index, (x, z) in enumerate(nodes, 1):
        steps.append(
            {
                "id": f"s{index}_move",
                "action": "move",
                "target": [x, z],
                "goal": f"移动到 ({x:.0f}, {z:.0f})",
            }
        )
        steps.append(
            {
                "id": f"s{index}_interact",
                "action": "interact",
                "target": [x, z],
                "goal": f"在 ({x:.0f}, {z:.0f}) 交互",
            }
        )
    return {
        "note": "示意坐标；用于沙盘 NavMesh 闭环执行验证，不是游戏真实坐标",
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="sandbox/data/exec_plan.json")
    parser.add_argument("--bad", action="store_true", help="追加一个不可达步骤，用于验证重试/暂停")
    args = parser.parse_args()
    nodes = [(-20.0, -20.0), (-8.0, -8.0), (8.0, 8.0), (20.0, 20.0)]
    plan = build(nodes)
    if args.bad:
        plan["steps"].append(
            {"id": "s5_unreachable", "action": "move", "target": [500.0, 500.0], "goal": "不可达目标"}
        )
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"steps": len(plan["steps"]), "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
