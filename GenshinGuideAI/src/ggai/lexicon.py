"""领域词表纠错：对 OCR 文本做受控的模糊替换（仅长词、编辑距离≤1）。"""
from __future__ import annotations

from .metrics import levenshtein

# 纳塔 5.0 相关专名与常用词；宁可少纠，不可乱改
DEFAULT_TERMS: list[str] = [
    "归火圣夜巡礼",
    "回声之子",
    "圣火竞技场",
    "乌沙博蒂",
    "冲天转转",
    "嵴锋龙",
    "古名",
    "大灵",
    "圣火",
    "话事处",
    "纳塔",
    "派蒙",
    "卡齐娜",
    "帕加尔",
    "森珀娅",
    "特拉科",
    "玛薇卡",
    "希诺宁",
    "茜特菈莉",
    "夜魂",
    "着急",
    "拿到",
    "由来已久",
    "史诗",
]


def correct_text(text: str, terms: list[str] | None = None, max_edits: int = 1) -> str:
    """把与词表词编辑距离 ≤ max_edits 的片段替换为标准写法。

    只处理长度 ≥3 的词，避免把短词误替换。
    """
    if not text:
        return text
    terms = terms or DEFAULT_TERMS
    spans: list[tuple[int, int, str]] = []
    for term in sorted(terms, key=len, reverse=True):
        if len(term) < 3:
            continue
        for window_len in (len(term),):
            if window_len < 3:
                continue
            for start in range(0, len(text) - window_len + 1):
                window = text[start : start + window_len]
                if term in window:
                    continue
                if window[0] in "和与的了在是也都就要把被这那很更还又":
                    continue
                if not all("\u4e00" <= ch <= "\u9fff" for ch in window):
                    continue
                if levenshtein(window, term) > max_edits:
                    continue
                end = start + window_len
                if any(not (end <= s or start >= e) for s, e, _ in spans):
                    continue
                spans.append((start, end, term))
    if not spans:
        return text
    spans.sort(key=lambda item: item[0])
    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        if start < cursor:
            continue
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def correct_project(project: dict, terms: list[str] | None = None) -> dict:
    """就地修正项目中的所有对话/任务文本，返回统计。"""
    stats = {"events": 0, "changed": 0}
    for event in project.get("events", []):
        stats["events"] += 1
        params = event.get("action", {}).get("params", {})
        for key in ("text", "quest_text"):
            value = params.get(key)
            if not isinstance(value, str) or not value:
                continue
            fixed = correct_text(value, terms)
            if fixed != value:
                params[key] = fixed
                stats["changed"] += 1
        observed = event.get("observed_result", {})
        if isinstance(observed, dict) and isinstance(observed.get("text"), str):
            fixed = correct_text(observed["text"], terms)
            if fixed != observed["text"]:
                observed["text"] = fixed
                stats["changed"] += 1
    return stats
