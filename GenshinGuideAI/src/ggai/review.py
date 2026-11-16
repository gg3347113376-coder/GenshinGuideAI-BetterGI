"""人工复核回填：把复核 CSV 的结论/修正写回项目 JSON，保留修改前后记录。"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

VALID = {"confirmed", "corrected", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def apply_review(
    project: dict,
    csv_path: str | Path,
    reviewer: str = "human",
    term_map: dict[str, str] | None = None,
) -> dict:
    """读取复核 CSV 并写回事件。

    CSV 列（至少）：序号、人工结论；可选：修正文本、修正说话人、复核备注。
    人工结论取值：confirmed / corrected / rejected / 空（跳过）。
    """
    rows = list(csv.DictReader(Path(csv_path).read_text(encoding="utf-8-sig").splitlines()))
    events = project.get("events", [])
    stats = {"rows": len(rows), "confirmed": 0, "corrected": 0, "rejected": 0, "skipped": 0, "errors": []}
    term_map = term_map or {}
    for row in rows:
        verdict = (row.get("人工结论") or "").strip().lower()
        if not verdict:
            stats["skipped"] += 1
            continue
        if verdict not in VALID:
            stats["errors"].append(f"未知结论：{verdict}")
            continue
        try:
            index = int(row.get("序号", "")) - 1
        except ValueError:
            stats["errors"].append(f"序号无效：{row.get('序号')}")
            continue
        if not (0 <= index < len(events)):
            stats["errors"].append(f"序号越界：{index + 1}")
            continue
        event = events[index]
        params = event.get("action", {}).get("params", {})
        before = {"text": params.get("text", ""), "speaker": params.get("speaker", "")}
        after = dict(before)
        if verdict == "corrected":
            new_text = (row.get("修正文本") or "").strip()
            new_speaker = (row.get("修正说话人") or "").strip()
            if new_text:
                after["text"] = new_text
            if new_speaker:
                after["speaker"] = new_speaker
            if after == before:
                stats["errors"].append(f"序号 {index + 1} 标为 corrected 但没有修改内容")
                continue
            if after["text"]:
                params["text"] = after["text"]
            if after["speaker"]:
                params["speaker"] = after["speaker"]
            event.setdefault("actor", {})["name"] = after["speaker"]
            if after["text"]:
                event.setdefault("observed_result", {})["text"] = after["text"]
        event["review"] = {
            "status": verdict,
            "by": reviewer,
            "at": _now(),
            "diff": {"before": before, "after": after} if verdict != "confirmed" else None,
        }
        stats[verdict] += 1
    return stats
