"""把复核 CSV 写回项目 JSON。

用法：
  python tools/apply_review.py --project runs\p002_full_v7.json --csv runs\review.csv --out runs\p002_reviewed.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402
from ggai.review import apply_review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reviewer", default="human")
    args = parser.parse_args()
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    stats = apply_review(project, args.csv, reviewer=args.reviewer)
    errors = protocol.validate(project)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:5]}, ensure_ascii=False))
        return 1
    Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, **stats, "out": args.out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
