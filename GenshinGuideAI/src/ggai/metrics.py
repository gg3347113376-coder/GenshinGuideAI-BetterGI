"""方向一/二的质量指标：覆盖率、OCR 相似度、说话人命中、时间误差。"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _norm(text: str) -> str:
    return re.sub(r"[\s，。！？、；：\"'“”‘’「」『』（）()【】\[\]…—－\-~·.,!?;:]", "", text or "")


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def text_similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return 1.0 - levenshtein(na, nb) / max(len(na), len(nb))


def project_coverage(project: dict) -> dict:
    events = project.get("events", [])
    total = len(events)
    with_evidence = sum(1 for e in events if any(v.get("path") for v in e.get("evidence", [])))
    with_coords = sum(
        1
        for e in events
        if (e.get("position", {}).get("map", {}) or {}).get("x") is not None
        and (e.get("position", {}).get("map", {}) or {}).get("y") is not None
    )
    with_review = sum(1 for e in events if (e.get("review") or {}).get("status") == "pending")
    confidences = [float(e.get("confidence", 0)) for e in events]
    return {
        "events": total,
        "with_evidence": with_evidence,
        "with_coords": with_coords,
        "review_pending": with_review,
        "mean_confidence": round(sum(confidences) / total, 3) if total else 0.0,
        "evidence_ratio": round(with_evidence / total, 3) if total else 0.0,
        "coords_ratio": round(with_coords / total, 3) if total else 0.0,
    }


def match_gold(project: dict, gold: list[dict], tolerance_s: float = 8.0) -> list[dict]:
    """把金标准条目匹配到最接近的 dialogue 事件。"""
    dialogues = [e for e in project.get("events", []) if e.get("action", {}).get("type") == "dialogue"]
    results = []
    for item in gold:
        t = float(item["t"])
        best = None
        best_dt = None
        for event in dialogues:
            dt = abs(float(event["video_time"]["start_s"]) - t)
            if best is None or dt < best_dt:
                best, best_dt = event, dt
        if best is None or best_dt > tolerance_s:
            results.append(
                {
                    "gold_t": t,
                    "matched": False,
                    "time_error_s": None,
                    "text_similarity": 0.0,
                    "speaker_match": False,
                    "gold_text": item["text"],
                    "pred_text": "",
                }
            )
            continue
        pred = best.get("action", {}).get("params", {})
        results.append(
            {
                "gold_t": t,
                "matched": True,
                "event_t": float(best["video_time"]["start_s"]),
                "time_error_s": round(best_dt, 2),
                "text_similarity": round(text_similarity(item["text"], pred.get("text", "")), 3),
                "speaker_match": pred.get("speaker", "") == item.get("speaker", ""),
                "gold_text": item["text"],
                "pred_text": pred.get("text", ""),
                "pred_speaker": pred.get("speaker", ""),
                "gold_speaker": item.get("speaker", ""),
            }
        )
    return results


def summarize_matches(matches: list[dict]) -> dict:
    n = len(matches)
    matched = [m for m in matches if m["matched"]]
    sims = [m["text_similarity"] for m in matched]
    exact = sum(1 for m in matched if m["text_similarity"] >= 0.999)
    return {
        "gold_items": n,
        "matched": len(matched),
        "match_rate": round(len(matched) / n, 3) if n else 0.0,
        "exact_match_rate": round(exact / len(matched), 3) if matched else 0.0,
        "mean_similarity": round(sum(sims) / len(sims), 3) if sims else 0.0,
        "speaker_accuracy": round(sum(1 for m in matched if m["speaker_match"]) / len(matched), 3) if matched else 0.0,
        "mean_time_error_s": round(sum(m["time_error_s"] for m in matched) / len(matched), 2) if matched else 0.0,
    }
