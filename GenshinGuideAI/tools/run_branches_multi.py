"""多 seed 分支评估并写入 sim_runs 表。

用法：python tools/run_branches_multi.py --seeds 20 --db runs/sim_runs.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.branches import BranchSpec, evaluate  # noqa: E402
from ggai.executor import Faults  # noqa: E402
from ggai.simstore import save_sim_run  # noqa: E402

DIRECT = [(5, 5), (10, 10), (15, 15)]
DETOUR = [(4, 16), (16, 16), (15, 15)]


def specs() -> list[BranchSpec]:
    return [
        BranchSpec(id="A_direct", name="直达路线", nodes=DIRECT, seed=0, changes="基线"),
        BranchSpec(
            id="B_detour",
            name="南侧绕行",
            nodes=DETOUR,
            seed=0,
            changes="沿南侧绕行，避开中央区域",
        ),
        BranchSpec(
            id="C_drift",
            name="直达+漂移",
            nodes=DIRECT,
            faults=Faults(drift_prob=0.2),
            seed=0,
            changes="环境加入 20% 位置漂移",
        ),
        BranchSpec(
            id="D_lost",
            name="直达+动作丢失",
            nodes=DIRECT,
            faults=Faults(lost_prob=0.2),
            seed=0,
            changes="环境加入 20% 动作丢失",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--db", default="runs/sim_runs.db")
    parser.add_argument("--out", default="runs/branches_multi.json")
    args = parser.parse_args()
    seeds = list(range(args.seeds))
    results = []
    for spec in specs():
        summary = evaluate(spec, seeds)
        results.append(summary)
        for run in summary["runs"]:
            if not run.get("valid"):
                continue
            save_sim_run(
                ROOT / args.db,
                project_id="proj_branches",
                params={
                    "branch_id": spec.id,
                    "nodes": [list(n) for n in spec.nodes],
                    "faults": {
                        "drift_prob": spec.faults.drift_prob,
                        "lost_prob": spec.faults.lost_prob,
                        "timeout_prob": spec.faults.timeout_prob,
                    },
                    "changes": spec.changes,
                },
                rules_ver=spec.rules_version,
                seed=run["seed"],
                status="completed" if run["completed"] else "paused",
                result={
                    "actions": run["actions"],
                    "retries": run["retries"],
                    "ticks": run["ticks"],
                    "paused_reason": run.get("paused_reason", ""),
                },
            )

    print("| 分支 | 完成率 | 动作均值±标准差 | 重试均值 | 时钟均值 |")
    print("|---|---|---|---|---|")
    for row in results:
        print(
            f"| {row['name']} | {row['completion_rate']:.0%} | "
            f"{row['actions_mean']} ± {row['actions_std']} | {row['retries_mean']} | {row['ticks_mean']} |"
        )
    winner = sorted(results, key=lambda r: (-r["completion_rate"], r["actions_mean"]))[0]
    payload = {"seeds": seeds, "results": results, "winner": winner["id"]}
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"winner": winner["id"], "db": str(ROOT / args.db), "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
