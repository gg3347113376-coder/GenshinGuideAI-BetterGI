"""对已有项目 JSON 应用领域词表纠错（不重跑 OCR）。

用法：python tools/apply_lexicon.py runs\p002_full_v6.json runs\p002_full_v7.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import lexicon, protocol  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("out")
    args = parser.parse_args()
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    stats = lexicon.correct_project(project)
    errors = protocol.validate(project)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:5]}, ensure_ascii=False))
        return 1
    Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, **stats, "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
