"""从逐帧 OCR 观测中抽取协议 v1 事件（v0.2：归一化 + 稳定去重 + 任务/距离分离）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .ocr import OcrItem
from .protocol import add_event, now_iso

DISTANCE = re.compile(r"(\d+)\s*m\b", re.IGNORECASE)
CJK = re.compile(r"[\u4e00-\u9fff]")
EDGE_PUNCT = "，。！？、；：\"'“”‘’「」『』（）()【】[]…—－-~·.,!?;:"
SIM_SAME = 0.90
STABLE_SAMPLES = 2


def plausible_text(text: str, min_cjk: int = 2, max_len: int = 60) -> bool:
    """过滤 OCR 噪声：必须有足够汉字、长度合理、不是纯拉丁/纯数字。"""
    if not text or len(text) > max_len:
        return False
    cjk = len(CJK.findall(text))
    if cjk < min_cjk:
        return False
    return cjk / max(1, len(text)) >= 0.5


@dataclass
class Observation:
    t_s: float
    regions: dict[str, list[OcrItem]] = field(default_factory=dict)
    frame_path: str | None = None

    def texts(self, region: str) -> list[OcrItem]:
        return [i for i in self.regions.get(region, []) if i.text.strip()]


def norm_text(text: str) -> str:
    t = re.sub(r"\s+", "", text or "")
    t = t.strip(EDGE_PUNCT)
    # 清理 OCR 在行首/行尾产生的「一」噪声（如「一一『回声之子」」）
    while len(t) > 3 and t[0] == "一":
        t = t[1:]
    while len(t) > 3 and t[-1] == "一":
        t = t[:-1]
    return t.strip(EDGE_PUNCT)


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class Stability:
    """同一个候选文本连续出现 N 次才认为稳定。"""

    def __init__(self, samples: int = STABLE_SAMPLES, recent: int = 3) -> None:
        self.samples = samples
        self.candidate = ""
        self.count = 0
        self.recent: list[str] = []
        self.recent_cap = recent

    def push(self, text: str) -> str | None:
        """返回应当发射的文本；未稳定或与最近几条重复时返回 None。"""
        if not text:
            return None
        if similar(text, self.candidate) >= 0.95:
            self.count += 1
        else:
            self.candidate = text
            self.count = 1
        if self.count < self.samples:
            return None
        if any(similar(text, old) >= SIM_SAME for old in self.recent):
            return None
        self.recent.append(text)
        self.recent = self.recent[-self.recent_cap:]
        return text


def _box(item: OcrItem) -> list[int]:
    return [item.box[0], item.box[1], item.box[2], item.box[3]]


def _pick_lines(items: list[OcrItem]) -> tuple[str, str]:
    """从字幕条带结果中区分说话人与台词。

    规则：最长的是台词；说话人必须位于台词上方（条带 y 更小）、长度 2–10、
    且不以标点结尾。避免把短台词误判成说话人。
    """
    cleaned = [(norm_text(i.text), i) for i in items]
    cleaned = [(t, i) for t, i in cleaned if plausible_text(t, min_cjk=2, max_len=60)]
    if not cleaned:
        return "", ""
    cleaned.sort(key=lambda x: -len(x[0]))
    line, line_item = cleaned[0]
    if len(line) <= 4 and not any(ch in line for ch in "，。！？、"):
        return "", line  # 只有名字，没有台词
    speaker = ""
    for text, item in cleaned[1:]:
        if _valid_speaker(text) and item.box[1] < line_item.box[1]:
            speaker = text
            break
    return line, speaker


def _valid_speaker(text: str) -> bool:
    """说话人只允许 2–6 个纯汉字；过滤选项气泡与 OCR 字母/数字噪声。"""
    if not (2 <= len(text) <= 6):
        return False
    return all("\u4e00" <= ch <= "\u9fff" for ch in text)


def canonicalize_speakers(events: list[dict]) -> None:
    """把同一说话人的 OCR 变体归并到出现次数最多的写法。"""
    from collections import Counter

    counts: Counter[str] = Counter()
    for event in events:
        speaker = (event.get("action", {}).get("params", {}) or {}).get("speaker", "")
        if speaker:
            counts[speaker] += 1
    names = list(counts)
    clusters: list[list[str]] = []
    for name in sorted(names, key=lambda n: -counts[n]):
        placed = False
        for cluster in clusters:
            if any(similar(name, member) >= 0.6 or name in member or member in name for member in cluster):
                cluster.append(name)
                placed = True
                break
        if not placed:
            clusters.append([name])
    mapping: dict[str, str] = {}
    for cluster in clusters:
        def core_score(name: str) -> int:
            return sum(1 for other in cluster if other != name and name in other)
        canonical = max(cluster, key=lambda n: (core_score(n), counts[n], -len(n)))
        if counts[canonical] >= 1 and len(cluster) > 1:
            for member in cluster:
                mapping[member] = canonical
    for event in events:
        params = event.get("action", {}).get("params", {})
        speaker = params.get("speaker", "")
        if speaker in mapping:
            params["speaker"] = mapping[speaker]
            event["actor"]["name"] = mapping[speaker]


def extract_events(
    project: dict,
    source_id: str,
    observations: list[Observation],
    segment_id: str | None = None,
) -> list[dict]:
    events: list[dict] = []
    quest_stable = Stability()
    subtitle_stable = Stability()
    last_quest_state = ""
    quest_memory: list[tuple[str, float]] = []
    known_speakers: list[str] = []

    for obs in sorted(observations, key=lambda o: o.t_s):
        # ---------- 任务追踪 ----------
        quest_items = obs.texts("quest_tracker")
        distance = None
        lines: list[str] = []
        for item in quest_items:
            match = DISTANCE.search(item.text)
            if match:
                distance = int(match.group(1))
            text = norm_text(DISTANCE.sub("", item.text))
            if plausible_text(text, min_cjk=3, max_len=40):
                lines.append(text)
        # 去重后按长度排序：最长的是任务名，其次是小标题
        unique: list[str] = []
        for line in sorted(lines, key=len, reverse=True):
            if all(similar(line, u) < 0.9 for u in unique):
                unique.append(line)
        # 记忆补齐：10 秒内出现过的行，本次没识别到也补上，避免条带漏检导致来回抖动
        merged = list(unique)
        for text, seen_t in quest_memory:
            if obs.t_s - seen_t <= 10 and all(similar(text, m) < 0.9 for m in merged):
                merged.append(text)
        for text in unique:
            quest_memory = [(t, ts) for t, ts in quest_memory if similar(t, text) < 0.9]
            quest_memory.append((text, obs.t_s))
        unique = sorted(merged, key=len, reverse=True)
        state = " | ".join(unique[:2])
        emitted = quest_stable.push(state) if state else None
        if emitted and similar(emitted, last_quest_state) < SIM_SAME:
            evidence = [
                {
                    "kind": "ocr",
                    "t_s": round(obs.t_s, 2),
                    "path": obs.frame_path or "",
                    "bbox": _box(item),
                    "text": item.text,
                    "note": "任务追踪",
                }
                for item in quest_items
            ]
            params = {"quest_text": emitted}
            if distance is not None:
                params["distance_m"] = distance
            add_event(
                project,
                {
                    "id": f"evt_{len(events) + 1:06d}",
                    "source_id": source_id,
                    "segment_id": segment_id,
                    "video_time": {
                        "start_s": round(max(0.0, obs.t_s - 1.0), 2),
                        "end_s": round(obs.t_s, 2),
                        "precision": "second",
                    },
                    "actor": {"kind": "player", "name": "", "confidence": 0.5},
                    "action": {
                        "type": "move",
                        "params": params,
                        "method": "inferred",
                        "notes": "由任务追踪文本推断目标移动",
                    },
                    "position": {
                        "map": {
                            "x": None,
                            "y": None,
                            "layer": "unknown",
                            "region": "",
                            "anchor": unique[0] if unique else "",
                            "error_m": None,
                            "method": "unknown",
                            "confidence": 0.0,
                        },
                        "world": {
                            "x": None,
                            "y": None,
                            "z": None,
                            "error_m": None,
                            "method": "unknown",
                            "confidence": 0.0,
                        },
                    },
                    "expected_result": {"text": "接近任务目标", "checks": []},
                    "observed_result": {"text": emitted, "checks": []},
                    "state_status": "observed",
                    "confidence": 0.6,
                    "evidence": evidence,
                    "review": {"status": "pending"},
                    "notes": "坐标未知：仅记录任务文本与距离",
                },
            )
            events.append(project["events"][-1])
            last_quest_state = emitted

        # ---------- 字幕/对话 ----------
        subtitle_items = obs.texts("subtitle")
        line, speaker = _pick_lines(subtitle_items)
        if not speaker:
            for item in obs.texts("speaker"):
                candidate = norm_text(item.text)
                if _valid_speaker(candidate):
                    speaker = candidate
                    break
        if speaker:
            matched = next((k for k in known_speakers if similar(speaker, k) >= 0.7), None)
            if matched:
                speaker = matched
            else:
                known_speakers.append(speaker)
        emitted_line = subtitle_stable.push(line) if line else None
        if emitted_line:
            evidence = [
                {
                    "kind": "ocr",
                    "t_s": round(obs.t_s, 2),
                    "path": obs.frame_path or "",
                    "bbox": _box(item),
                    "text": item.text,
                    "note": "对话字幕",
                }
                for item in subtitle_items
            ]
            add_event(
                project,
                {
                    "id": f"evt_{len(events) + 1:06d}",
                    "source_id": source_id,
                    "segment_id": segment_id,
                    "video_time": {
                        "start_s": round(obs.t_s, 2),
                        "end_s": round(obs.t_s, 2),
                        "precision": "second",
                    },
                    "actor": {
                        "kind": "npc" if speaker else "unknown",
                        "name": speaker,
                        "confidence": 0.6 if speaker else 0.3,
                    },
                    "action": {
                        "type": "dialogue",
                        "params": {"text": emitted_line, **({"speaker": speaker} if speaker else {})},
                        "method": "observed",
                    },
                    "position": {
                        "map": {
                            "x": None,
                            "y": None,
                            "layer": "unknown",
                            "region": "",
                            "anchor": "",
                            "error_m": None,
                            "method": "unknown",
                            "confidence": 0.0,
                        },
                        "world": {
                            "x": None,
                            "y": None,
                            "z": None,
                            "error_m": None,
                            "method": "unknown",
                            "confidence": 0.0,
                        },
                    },
                    "expected_result": {"text": "台词推进", "checks": []},
                    "observed_result": {"text": emitted_line, "checks": []},
                    "state_status": "observed",
                    "confidence": 0.75,
                    "evidence": evidence,
                    "review": {"status": "pending"},
                    "notes": "",
                },
            )
            events.append(project["events"][-1])

    canonicalize_speakers(events)
    project["project"]["model_versions"]["rules"] = "ggai-0.3.0"
    project["project"]["model_versions"]["updated_at"] = now_iso()
    return events
