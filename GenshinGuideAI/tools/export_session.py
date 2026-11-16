r"""导出 DSH 会话记录：Markdown 可读版 + 原始 JSONL。

用法：
  python tools\export_session.py --session <session-id> --out <目录>
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

import zstandard

DSH_HOME = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))


def fmt_time(ms: int | float | None) -> str:
    if not ms:
        return ""
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def find_session(session_id: str) -> Path:
    matches = list(DSH_HOME.glob(f"sessions/*/{session_id}/session.v4.jsonl.zstd"))
    if not matches:
        raise FileNotFoundError(f"未找到会话：{session_id}")
    return matches[0]


def indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def truncate(text: str, limit: int) -> tuple[str, bool]:
    text = text or ""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def export(session_id: str, out_dir: Path) -> dict:
    source = find_session(session_id)
    with source.open("rb") as handle:
        raw = zstandard.ZstdDecompressor().stream_reader(handle).read().decode("utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "session.v4.jsonl").write_text(raw, encoding="utf-8")

    lines: list[str] = []
    header: dict = {}
    title = ""
    stats = {"turns": 0, "user": 0, "assistant": 0, "tools": 0, "results": 0}
    last_role = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        data = obj.get("data", {}) or {}
        if kind == "session":
            header = obj
            lines.append("# DSH 会话记录")
            lines.append("")
            lines.append(f"- 会话 ID：`{obj.get('id')}`")
            lines.append(f"- 工作区：`{obj.get('cwd')}`")
            lines.append(f"- 开始时间：{fmt_time(obj.get('createdAt'))}")
            continue
        if kind == "session/title":
            title = str(data.get("title", ""))
            continue
        if kind == "turn/start":
            stats["turns"] += 1
            lines.append("")
            lines.append(f"## 第 {data.get('turn')} 轮 · {fmt_time(obj.get('time'))}")
            lines.append("")
            last_role = ""
            continue
        if kind == "turn/end":
            reason = (data.get("reason") or {}).get("error")
            if reason:
                lines.append("")
                lines.append(f"> ⚠️ 本轮异常结束：{reason.get('message', '')}")
            continue
        if kind == "user/message":
            stats["user"] += 1
            lines.append("### 👤 用户")
            lines.append("")
            for block in data.get("content", []):
                if block.get("type") == "text":
                    lines.append(block.get("text", ""))
                    lines.append("")
            continue
        if kind == "assistant/message":
            blocks = (data.get("message") or {}).get("content", [])
            text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text" and b.get("text", "").strip()]
            if text_parts:
                stats["assistant"] += 1
                lines.append("### 🤖 助手")
                lines.append("")
                lines.append("\n\n".join(text_parts))
                lines.append("")
            for block in blocks:
                if block.get("type") != "tool-call":
                    continue
                stats["tools"] += 1
                args, cut = truncate(str(block.get("arguments", "")), 700)
                try:
                    pretty = json.dumps(json.loads(args), ensure_ascii=False, indent=2) if not cut else args
                except (ValueError, TypeError):
                    pretty = args
                lines.append(f"#### 🔧 工具调用 `{block.get('name')}`{'' if not cut else '（已截断）'}")
                lines.append("")
                lines.append(indent(pretty))
                lines.append("")
            continue
        if kind == "tool/result":
            stats["results"] += 1
            message = data.get("message") or {}
            texts = [b.get("text", "") for b in message.get("content", []) if b.get("type") == "text"]
            body, cut = truncate("\n".join(texts), 500)
            flag = "（已截断）" if cut else ""
            lines.append(f"#### 📄 工具结果{flag}")
            lines.append("")
            lines.append(indent(body))
            lines.append("")
            continue
        if kind == "goal/change":
            goal = data.get("goal") or {}
            lines.append(f"#### 🎯 目标变更：{data.get('operation')} (roundsStarted={data.get('roundsStarted')})")
            lines.append("")
            lines.append(indent(str(goal.get("objective", ""))))
            lines.append("")
            continue
        if kind == "compaction/summary":
            text = str(data.get("summary") or data.get("text") or "")
            lines.append("#### 🧭 上下文压缩摘要")
            lines.append("")
            lines.append(indent(truncate(text, 2000)[0]))
            lines.append("")
            continue

    preamble = [
        "",
        f"- 标题：{title}" if title else "",
        f"- 轮次：{stats['turns']}",
        f"- 用户消息：{stats['user']} · 助手消息：{stats['assistant']} · 工具调用：{stats['tools']} · 工具结果：{stats['results']}",
        "- 说明：工具参数与结果做了截断；完整原始记录见同目录 `session.v4.jsonl`。",
        "",
    ]
    insert_at = 4
    lines[insert_at:insert_at] = [line for line in preamble if line != ""]
    (out_dir / "对话全文.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"session": session_id, "out": str(out_dir), **stats, "lines": len(raw.splitlines())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default=os.environ.get("DSH_SESSION_ID", ""))
    parser.add_argument("--out", default="runs/session_export")
    args = parser.parse_args()
    if not args.session:
        print(json.dumps({"error": "缺少 --session"}, ensure_ascii=False))
        return 1
    result = export(args.session, Path(args.out))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
