r"""把项目 JSON 导出为人工复核 CSV，并标出可疑事件。

用法：
  python tools/make_review.py runs\p002_300s.json runs\p002_300s_review.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SUSPICIOUS_EDGE = re.compile(r"^[一人一]|[一]$")
PUNCT = "，。！？、；：\"'“”‘’「」『』（）()【】[]…—－-~·.,!?;:"


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def flags_for(event: dict) -> list[str]:
    flags: list[str] = []
    if event["confidence"] < 0.6:
        flags.append("低置信")
    action = event["action"]
    params = action.get("params", {})
    text = params.get("text") or params.get("quest_text") or ""
    if action["type"] == "dialogue":
        if len(text) < 5:
            flags.append("文本过短")
        speaker = params.get("speaker", "")
        if speaker and (len(speaker) > 8 or any(ch in speaker for ch in PUNCT)):
            flags.append("说话人可疑")
    if SUSPICIOUS_EDGE.search(text):
        flags.append("首尾噪声")
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
        if len(parts) > 1 and parts[0] == parts[-1]:
            flags.append("任务文本重复")
    if not event.get("evidence"):
        flags.append("无证据")
    return flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("out")
    args = parser.parse_args()
    project = load(args.project)
    rows = []
    stats = {"total": 0, "flagged": 0, "by_type": {}, "by_flag": {}}
    for index, event in enumerate(project.get("events", []), 1):
        action = event["action"]
        params = action.get("params", {})
        flags = flags_for(event)
        stats["total"] += 1
        stats["by_type"][action["type"]] = stats["by_type"].get(action["type"], 0) + 1
        for flag in flags:
            stats["by_flag"][flag] = stats["by_flag"].get(flag, 0) + 1
        if flags:
            stats["flagged"] += 1
        evidence = event.get("evidence") or [{}]
        rows.append(
            {
                "序号": index,
                "时间s": event["video_time"]["start_s"],
                "类型": action["type"],
                "说话人": params.get("speaker", ""),
                "文本": (params.get("text") or params.get("quest_text") or "")[:200],
                "置信度": event["confidence"],
                "标记": ",".join(flags),
                "证据帧": evidence[0].get("path", ""),
                "人工结论": "",
                "修正文本": "",
                "修正说话人": "",
                "复核备注": "",
            }
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["序号"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"csv": str(out), **stats}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
