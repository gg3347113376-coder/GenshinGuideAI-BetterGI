"""归档沙盘执行结果到 exec_runs 表，或列出已有执行记录。

用法：
  python tools/archive_exec.py --result sandbox/data/exec_result.json
  python tools/archive_exec.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.execstore import list_exec_runs, save_exec_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", default="sandbox/data/exec_result.json")
    parser.add_argument("--db", default="runs/sim_runs.db")
    parser.add_argument("--env", default="godot_sandbox")
    parser.add_argument("--sim-run-id", default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    db = ROOT / args.db

    if args.list:
        rows = list_exec_runs(db)
        for row in rows:
            print(
                f"{row['created_at']}  {row['id']}  env={row['env']}  status={row['status']}  "
                f"steps={len(row['report'].get('results', []))}"
            )
        print(json.dumps({"count": len(rows)}, ensure_ascii=False))
        return 0

    path = ROOT / args.result
    if not path.exists():
        print(json.dumps({"error": f"缺少 {path}"}, ensure_ascii=False))
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    run_id = save_exec_run(
        db,
        env=args.env,
        status=str(report.get("state", "unknown")),
        report=report,
        sim_run_id=args.sim_run_id,
    )
    print(json.dumps({"id": run_id, "env": args.env, "status": report.get("state"), "db": str(db)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
