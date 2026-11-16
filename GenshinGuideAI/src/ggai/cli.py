"""命令行入口：init / validate / import / export / stats。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import protocol, store


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    project = protocol.new_project(args.id, args.name, args.description)
    protocol.dump_project(project, path)
    print(f"已创建项目模板：{path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    project = protocol.load_project(args.path)
    errors = protocol.validate(project, Path(args.path).resolve().parent)
    if errors:
        print(f"校验失败：{len(errors)} 个问题")
        for err in errors[:50]:
            print("  -", err)
        return 1
    summary = protocol.summarise(project)
    print("校验通过：", json.dumps(summary, ensure_ascii=False))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    project = protocol.load_project(args.json)
    errors = protocol.validate(project, Path(args.json).resolve().parent)
    if errors:
        print(f"拒绝导入：协议校验失败（{len(errors)} 个问题）")
        for err in errors[:20]:
            print("  -", err)
        return 1
    result = store.import_project(project, args.db)
    print("已导入：", json.dumps(result, ensure_ascii=False))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    project = store.export_project(args.db, args.project_id)
    protocol.dump_project(project, args.json)
    print(f"已导出：{args.json}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
        project = store.export_project(path, args.project_id)
    else:
        project = protocol.load_project(path)
    print(json.dumps(protocol.summarise(project), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ggai", description=f"GenshinGuideAI v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="创建空的协议 v1 项目")
    p.add_argument("path")
    p.add_argument("--id", default="proj_demo")
    p.add_argument("--name", default="未命名项目")
    p.add_argument("--description", default="")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="校验项目 JSON")
    p.add_argument("path")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("import", help="导入 JSON 到 SQLite")
    p.add_argument("json")
    p.add_argument("db")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("export", help="从 SQLite 导出 JSON")
    p.add_argument("db")
    p.add_argument("json")
    p.add_argument("--project-id", default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("stats", help="查看统计（JSON 或 DB）")
    p.add_argument("path")
    p.add_argument("--project-id", default=None)
    p.set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
