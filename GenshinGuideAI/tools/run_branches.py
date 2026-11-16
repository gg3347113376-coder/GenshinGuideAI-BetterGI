"""自由推演分支比较（P5）：同初始状态、不同路线/环境参数。

用法：python tools/run_branches.py --out runs/branches.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.branches import BranchSpec, compare  # noqa: E402
from ggai.executor import Faults  # noqa: E402

DIRECT = [(5, 5), (10, 10), (15, 15)]
DETOUR = [(4, 16), (16, 16), (15, 15)]


def build_specs() -> list[BranchSpec]:
    return [
        BranchSpec(id="A_direct", name="直达路线", nodes=DIRECT, seed=7, changes="基线"),
        BranchSpec(
            id="B_detour",
            name="南侧绕行",
            nodes=DETOUR,
            seed=7,
            changes="路线改为沿南侧绕行，避开中央区域",
        ),
        BranchSpec(
            id="C_drift",
            name="直达+漂移环境",
            nodes=DIRECT,
            faults=Faults(drift_prob=0.2),
            seed=7,
            changes="环境加入 20% 位置漂移",
        ),
        BranchSpec(
            id="D_invalid",
            name="穿墙路线（应判无效）",
            nodes=[(5, 5), (10, 10), (15, 15)],
            walls={(10, 10)},
            seed=7,
            changes="把中间节点放进墙里，验证约束检查",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runs/branches.json")
    args = parser.parse_args()
    result = compare(build_specs())
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("| 分支 | 有效 | 完成 | 动作 | 重试 | 时钟 | 暂停 |")
    print("|---|---|---|---|---|---|---|")
    for row in result["branches"]:
        print(
            f"| {row['name']} | {row.get('valid')} | {row.get('completed', '')} | "
            f"{row.get('actions', '')} | {row.get('retries', '')} | {row.get('ticks', '')} | {row.get('pauses', '')} |"
        )
    print(json.dumps({"winner": result["winner"], "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
