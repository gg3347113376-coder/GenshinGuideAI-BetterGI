"""片段分类：根据字幕是否存在，把视频切成 dialogue / travel 两类（低置信度）。"""
from __future__ import annotations

from dataclasses import dataclass

from .extract import Observation, norm_text


@dataclass
class Span:
    start_s: float
    end_s: float
    kind: str
    confidence: float
    notes: str


def classify_segments(
    observations: list[Observation],
    min_duration_s: float = 4.0,
    total_end_s: float | None = None,
) -> list[dict]:
    """把采样点序列压成片段。

    规则：采样子幕有文本 → dialogue；否则 → travel（未细分过场，避免过度推断）。
    相邻同类合并；短于 min_duration_s 的片段并入前一段。
    """
    if not observations:
        return []
    points: list[tuple[float, str]] = []
    for obs in sorted(observations, key=lambda o: o.t_s):
        has_subtitle = any(len(norm_text(i.text)) >= 2 for i in obs.regions.get("subtitle", []))
        points.append((obs.t_s, "dialogue" if has_subtitle else "travel"))

    spans: list[Span] = []
    for t_s, kind in points:
        if spans and spans[-1].kind == kind:
            spans[-1].end_s = t_s
        else:
            if spans:
                spans[-1].end_s = max(spans[-1].end_s, t_s)
            spans.append(Span(start_s=t_s, end_s=t_s, kind=kind, confidence=0.0, notes=""))

    end = total_end_s if total_end_s is not None else points[-1][0]
    if spans:
        spans[-1].end_s = max(spans[-1].end_s, end)

    # 短片段并入前一段
    merged: list[Span] = []
    for span in spans:
        if merged and (span.end_s - span.start_s) < min_duration_s:
            merged[-1].end_s = span.end_s
        else:
            merged.append(span)

    # 合并后可能产生相邻同类，再压一次
    final_spans: list[Span] = []
    for span in merged:
        if final_spans and final_spans[-1].kind == span.kind:
            final_spans[-1].end_s = span.end_s
        else:
            final_spans.append(span)
    merged = final_spans

    result = []
    for index, span in enumerate(merged, 1):
        duration = max(0.1, span.end_s - span.start_s)
        confidence = 0.65 if span.kind == "dialogue" else 0.35
        result.append(
            {
                "id": f"seg_{index:03d}",
                "source_id": "src_1",
                "start_s": round(span.start_s, 2),
                "end_s": round(span.end_s, 2),
                "kind": span.kind,
                "confidence": confidence,
                "notes": (
                    "字幕存在，判定为对话片段"
                    if span.kind == "dialogue"
                    else "无字幕片段；未细分跑图/过场"
                ),
            }
        )
    return result


def coverage(segments: list[dict]) -> dict:
    dialogue = sum(s["end_s"] - s["start_s"] for s in segments if s["kind"] == "dialogue")
    total = sum(s["end_s"] - s["start_s"] for s in segments)
    return {
        "total_s": round(total, 1),
        "dialogue_s": round(dialogue, 1),
        "dialogue_ratio": round(dialogue / total, 3) if total else 0.0,
        "segments": len(segments),
    }
