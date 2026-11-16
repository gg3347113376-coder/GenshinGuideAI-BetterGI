"""Positioned OCR, conservative ASR alternatives and guide-only waypoint candidates."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .planning import dump, sha256
from .metrics import levenshtein

ANCHOR_TYPES = {"传送锚点": "TeleportWaypoint", "七天神像": "Goddess", "秘境": "Domain"}
ELIGIBLE = {"map_region", "selected_anchor", "selected_region", "quest_tracker", "interaction_prompt", "subtitle", "tutorial"}


def compact(text):
    return re.sub(r"[\W_]+", "", text)


def catalog_points(data):
    return [dict(point, scene_id=scene["sceneId"]) for scene in data["data"] for point in scene["points"]]


def region_terms(points):
    return {v for p in points for v in [p.get("country", ""), *p.get("areas", [])] if len(v) >= 2}


def classify_frame(frame_id, rows, width, height, regions):
    normalized = []
    for i, (quad, text, score) in enumerate(rows or [], 1):
        xs, ys = zip(*quad)
        normalized.append({"id": f"{frame_id}_text_{i:03d}", "text": text, "confidence": float(score),
            "bbox": [min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height]})
    center = lambda row: ((row["bbox"][0] + row["bbox"][2]) / 2, (row["bbox"][1] + row["bbox"][3]) / 2)
    panel = any(center(r)[0] > .68 and center(r)[1] < .2 and any(t in r["text"] for t in ANCHOR_TYPES)
                and r["confidence"] >= .8 for r in normalized)
    map_status = any(re.search(r"\d+\s*/\s*\d+|第\d+层第\d+间", r["text"]) and center(r)[1] < .1 for r in normalized)
    map_labels = sum(any(v == compact(r["text"]) for v in regions) for r in normalized)
    scene = "map" if panel or (map_status and map_labels) else "gameplay_or_unknown"
    if any("设置" in r["text"] and center(r)[1] < .15 for r in normalized):
        scene = "unknown"
    for row in normalized:
        x, y = center(row); text = row["text"]; clean = compact(text)
        role, reason = "unclassified", "区域或用途不足以确认，不作为任务指令"
        if row["confidence"] < .8:
            role, reason = "uncertain", "OCR 分数不足；不自动补字"
        elif scene == "unknown":
            reason = "设置或未知界面，等待复核"
        elif panel and x > .68 and y < .2 and any(t in text for t in ANCHOR_TYPES):
            role, reason = "selected_anchor", "地图右侧选中目标面板的类型标题"
        elif panel and x > .68 and y < .2 and any(v in clean for v in regions):
            role, reason = "selected_region", "选中面板附近的区域文字，仅用于缩小候选"
        elif scene == "map" and y < .16 and ("声望" in text or re.search(r"第\d+层第\d+间|\d+\s*/\s*\d+", text)):
            role, reason = "persistent_ui", "地图顶栏状态或声望入口，不是任务或地名"
        elif re.fullmatch(r"[\d\s/.,%+\-]+", text):
            role, reason = "hud_or_overlay", "血量、计数或其他纯数字状态"
        elif "UID" in text.upper() or "bilibili" in text.lower() or y > .945:
            role, reason = "hud_or_overlay", "边缘状态、水印或作者进度条"
        elif clean in ("北", "东", "南", "西") and x < .4 and y < .45:
            role, reason = "editor_overlay", "方向标注，不是目的地名称"
        elif scene == "map":
            if clean in regions and x < .75:
                role, reason = "map_region", "地图区域标签；可见不等于被选中"
            elif x > .7 and any(v in text for v in ("宝箱", "神瞳", "挑战", "PS:", "进度条", "幻写灵", "解密")):
                role, reason = "editor_overlay", "地图侧边攻略图例，不是当前目标"
            else:
                role, reason = "map_context", "地图说明或菜单，不作为行动目标"
        elif "传送锚点" in text and ("按" in text or "靠近" in text or "打开" in text):
            role, reason = "tutorial", "教程提示，解释操作机制，不证明当前锚点已解锁"
        elif .78 < y < .945 and .1 < x < .9 and len(clean) >= 5:
            role, reason = "subtitle", "底部字幕；可能是讲解或角色台词，需要结合语音"
        elif .50 < x < .81 and .32 < y < .69 and 2 <= len(clean) <= 12:
            if re.match(r"^[A-Za-z0-9][\u4e00-\u9fff]", text):
                role, reason = "uncertain", "图标与文字粘连，不能作为精确交互文字"
            else:
                role, reason = "interaction_prompt", "交互提示区域；文字只对该提示有效"
        elif x < .34 and .17 < y < .37 and len(clean) >= 3:
            role, reason = "quest_tracker", "左侧任务追踪区域候选，仍需语境确认"
        elif x > .82 or y < .12:
            role, reason = "hud_or_overlay", "角色栏或顶部状态区域"
        row.update(role=role, eligible=role in ELIGIBLE, reason=reason)
    return {"evidence_id": frame_id, "scene": scene, "rows": normalized}


def anchor_candidates(frame, points):
    rows = frame["rows"]
    selected = [r for r in rows if r["role"] == "selected_anchor"]
    visible = [r for r in rows if r["eligible"] and any(t in r["text"] for t in ANCHOR_TYPES)]
    title = " ".join(r["text"] for r in selected)
    anchor_type = next((v for k, v in ANCHOR_TYPES.items() if k in title), None)
    if anchor_type is None:
        types = {v for r in visible for k, v in ANCHOR_TYPES.items() if k in r["text"]}
        anchor_type = next(iter(types)) if len(types) == 1 else "unknown"
    regional = [r for r in rows if r["role"] in ("selected_region", "map_region")]
    selected_regions = [r for r in regional if r["role"] == "selected_region"]
    used_regions = selected_regions or regional
    labels = sorted({v for r in used_regions for v in region_terms(points) if v in compact(r["text"])})
    candidates = []
    if selected and labels and anchor_type != "unknown":
        for point in points:
            type_ok = point["type"].endswith("Domain") if anchor_type == "Domain" else point["type"] == anchor_type
            # Map-wide labels are alternatives; only the selected panel can intersect regions.
            matches = [v in [point.get("country"), *point.get("areas", [])] for v in labels]
            if type_ok and (all(matches) if selected_regions else any(matches)):
                candidates.append({"scene_id": point["scene_id"], "id": point["id"], "name": point["name"],
                                   "type": point["type"], "areas": point.get("areas", [])})
    status = "not_identified"
    if visible:
        status = "type_only" if anchor_type != "unknown" else "ambiguous_type"
    if candidates:
        status = "candidate_unique" if len(candidates) == 1 else "ambiguous_candidates"
    return {"frame_id": frame["evidence_id"], "anchor_type": anchor_type, "identity_status": status,
            "selected_panel_visible": bool(selected), "text_ids": [r["id"] for r in visible],
            "region_text_ids": [r["id"] for r in used_regions], "region_labels": labels,
            "candidates": candidates, "verified_point_id": None, "verified_coordinates": None,
            "current_player_unlocked": "unknown",
            "note": "作者视频的文字候选。唯一候选也未经过地图定位核验；不能证明用户当前解锁状态。"}


def compare_transcripts(evidence, retry, frames, vocabulary):
    frame_times = {e["id"]: e["time"]["start_s"] for e in evidence if e["kind"] == "frame"}
    result = []
    for item in evidence:
        if item["kind"] != "asr":
            continue
        start, end = item["time"]["start_s"], item["time"]["end_s"]
        overlap = [r for r in retry if min(r["end"], end) - max(r["start"], start) > .15]
        word_aligned = bool(overlap) and all(r.get("words") for r in overlap)
        if word_aligned:
            words = [w for r in overlap for w in r["words"] if start <= (w["start"] + w["end"]) / 2 <= end]
            candidate = "".join(w["word"] for w in words).strip() or None
        else:
            candidate = "".join(r["text"] for r in overlap).strip() or None
        context_only = not word_aligned and any(r["start"] < start - .3 or r["end"] > end + .3 for r in overlap)
        proposed = sorted(t for t in vocabulary if candidate and not context_only and t in compact(candidate) and t not in compact(item["text"]))
        support = []
        for term in proposed:
            for frame in frames:
                if start - 3 <= frame_times[frame["evidence_id"]] <= end + 3:
                    for row in frame["rows"]:
                        if row["eligible"] and term in compact(row["text"]):
                            support.append({"term": term, "frame_id": frame["evidence_id"], "text_id": row["id"]})
        lexical = []
        original_clean = compact(item["text"])
        for frame in frames:
            if not start - 3 <= frame_times[frame["evidence_id"]] <= end + 3:
                continue
            for row in frame["rows"]:
                term = compact(row["text"])
                if row["role"] not in ("map_region", "selected_region", "selected_anchor", "interaction_prompt") or term not in vocabulary or len(term) < 3 or term in original_clean:
                    continue
                windows = [original_clean[i:i + len(term)] for i in range(len(original_clean) - len(term) + 1)]
                matches = [w for w in windows if 0 < levenshtein(w, term) <= (1 if len(term) == 3 else 2)
                           and sum(a == b for a, b in zip(w, term)) >= 2]
                if matches:
                    word = min(matches, key=lambda w: levenshtein(w, term))
                    lexical.append({"original_fragment": word, "candidate": term, "frame_id": frame["evidence_id"],
                                    "text_id": row["id"], "status": "proposed_not_replaced"})
        status = "not_retranscribed" if candidate is None else ("context_only" if context_only else ("agrees" if compact(candidate) == compact(item["text"]) else "alternative_unverified"))
        result.append({"evidence_id": item["id"], "original": item["text"], "alternative": candidate,
                       "status": status, "proposed_terms": proposed, "corroborated_terms": support, "lexical_candidates": lexical})
    return result


def instruction_hints(project):
    """Coverage checks for explicit narration; not a complete language parser."""
    patterns = {"fight": r"(?:把|将).{0,8}(?:怪|敌人).{0,6}(?:清|消灭)|(?:击败|消灭).{0,6}(?:怪|敌人)",
                "interact": r"(?:开启|打开).{0,8}宝箱",
                "teleport": r"(?:我们|你|先).{0,8}传送(?:到|至)|(?:点击|选择).{0,12}传送",
                "move_to": r"(?:朝|往|向).{0,12}(?:走|移动|前进)|(?:要到|走到).{0,15}(?:底下|下面|树下)"}
    hints = []
    for e in project["evidence_index"]:
        if e["kind"] != "asr":
            continue
        text = compact(e["text"])
        # Negation and hypothetical examples cannot establish mandatory actions.
        if any(word in text for word in ("不要", "不用", "不能", "无需", "如果", "比如", "例如")):
            continue
        for action, pattern in patterns.items():
            if re.search(pattern, text):
                hints.append({"evidence_id": e["id"], "action_id": action, "text": e["text"]})
    return hints


def grounded_input(project):
    g = project["grounding"]
    frames = [{"evidence_id": f["evidence_id"], "scene": f["scene"],
               "text": [{"text": r["text"], "role": r["role"]} for r in f["rows"] if r["eligible"] and r["role"] != "map_region"]} for f in g["frames"]]
    transcripts = []
    seen_alternatives = {}
    for t in g["transcripts"]:
        alternative = t["alternative"] if t["status"] != "context_only" else None
        if alternative and alternative in seen_alternatives:
            alternative = "与 " + seen_alternatives[alternative] + " 共享同一段复听，不能推断为重复指令"
        elif alternative:
            seen_alternatives[alternative] = t["evidence_id"]
        transcripts.append({"evidence_id": t["evidence_id"], "original": t["original"], "alternative_unverified": alternative,
                            "ocr_supported_terms": sorted({c["term"] for c in t["corroborated_terms"]}),
                            "spelling_candidates": sorted({c["original_fragment"] + " → " + c["candidate"] for c in t["lexical_candidates"]})})
    anchors = [{"frame_id": a["frame_id"], "type": a["anchor_type"], "region": a["region_labels"],
                "candidate_count": len(a["candidates"]), "identity_status": a["identity_status"],
                "verified_point_id": None, "current_player_unlocked": "unknown"} for a in g["anchors"] if a["identity_status"] != "not_identified"]
    # Excluded OCR and unconstrained VLM narratives remain on disk, not in the task prompt.
    return {"frames": frames, "transcripts_in_time_order": transcripts, "anchors": anchors,
            "explicit_instruction_hints": instruction_hints(project)}


def review_plan(project):
    g = project["grounding"]; steps = project["task_plan"]["steps"]; issues = []
    eligible_text = {compact(r["text"]) for f in g["frames"] for r in f["rows"] if r["eligible"]}
    raw_asr = "".join(compact(e["text"]) for e in project["evidence_index"] if e["kind"] == "asr")
    excluded = {r["text"] for f in g["frames"] for r in f["rows"] if r["role"] in ("persistent_ui", "editor_overlay")
                and len(compact(r["text"])) >= 3 and compact(r["text"]) not in eligible_text and compact(r["text"]) not in raw_asr}
    fields = [("goal", project["task_plan"]["goal"])] + [(s["id"], " ".join([s["title"], s["intent"], s["params"].get("target_label", "")])) for s in steps]
    supported_words = raw_asr + "".join(compact(t["alternative"] or "") for t in g["transcripts"] if t["status"] != "context_only")
    supported_words += "".join(compact(c["candidate"]) for t in g["transcripts"] for c in t["lexical_candidates"])
    supported_words += "".join(compact(r["text"]) for f in g["frames"] for r in f["rows"] if r["eligible"] and r["role"] != "map_region")
    unconfirmed_regions = {r["text"] for f in g["frames"] for r in f["rows"] if r["role"] == "map_region" and compact(r["text"]) not in supported_words}
    combat_supported = any(word in supported_words for word in ("怪", "敌人", "击败", "战斗", "丘丘"))
    for sid, text in fields:
        if not combat_supported and any(word in text for word in ("怪物", "敌人", "清怪", "击败")):
            issues.append({"step_id": sid, "code": "unsupported_combat_target", "detail": "现有文字证据没有怪物/战斗目标，不能从听不清的地形词臆造敌人"})
        if any(compact(word) in compact(text) for word in unconfirmed_regions):
            issues.append({"step_id": sid, "code": "unconfirmed_region_as_goal", "detail": "引用了只在地图背景上出现、未获解说或选中面板支持的区域名称"})
        if any(compact(word) in compact(text) for word in excluded):
            issues.append({"step_id": sid, "code": "ui_text_as_goal", "detail": "任务或目标引用了被排除的常驻界面/作者图例"})
    for step in steps:
        label = step["params"].get("target_label", "")
        if step["action_id"] == "teleport":
            if not any(word in label for word in ("锚点", "神像", "秘境", "传送点")):
                issues.append({"step_id": step["id"], "code": "region_as_waypoint", "detail": "传送目标必须描述传送点，不能直接把区域当作锚点"})
            if not step["uncertainties"]:
                issues.append({"step_id": step["id"], "code": "unacknowledged_anchor_uncertainty", "detail": "当前无法核验具体锚点与解锁状态，必须明确记录待核验"})
        if step["action_id"] == "interact" and any(word in label for word in ("锚点", "神像", "传送点")):
            selected_asr = [e["text"] for e in project["evidence_index"] if e["kind"] == "asr" and e["id"] in step["evidence_ids"]]
            selected_ocr = [r["text"] for f in g["frames"] if f["evidence_id"] in step["evidence_ids"] for r in f["rows"] if r["eligible"]]
            if not any(re.search(r"(?:解锁|激活).{0,10}(?:锚点|传送|神像)|(?:锚点|传送|神像).{0,10}(?:解锁|激活)", text) for text in selected_asr + selected_ocr):
                issues.append({"step_id": step["id"], "code": "unsupported_anchor_activation", "detail": "提到或到达传送锚点不等于解锁；这一步没有激活/解锁指令证据"})
        for field, role in [("target_text", "interaction_prompt"), ("option_text", "dialogue_option")]:
            value = step["params"].get(field)
            if not value:
                continue
            matches = [r for f in g["frames"] if f["evidence_id"] in step["evidence_ids"] for r in f["rows"]
                       if r["role"] == role and compact(r["text"]) == compact(value)]
            if not matches:
                issues.append({"step_id": step["id"], "code": "unsupported_exact_text", "detail": field + " 缺少该步骤所引用画面的精确提示文字"})
            elif value not in step["params"].get("target_label", ""):
                issues.append({"step_id": step["id"], "code": "interaction_target_mismatch", "detail": "交互提示存在，但与描述的目标不一致，需要复核"})
    for hint in instruction_hints(project):
        if not any(s["action_id"] == hint["action_id"] and hint["evidence_id"] in s["evidence_ids"] for s in steps):
            issues.append({"step_id": "plan", "code": "uncovered_instruction",
                           "detail": hint["evidence_id"] + " 的明确指令尚未对应 " + hint["action_id"] + " 步骤：" + hint["text"]})
    regions = {r["text"] for f in g["frames"] for r in f["rows"] if r["role"] == "map_region"}
    for step in steps:
        if step["action_id"] == "teleport" and step["params"].get("target_label") in regions:
            issues.append({"step_id": step["id"], "code": "region_as_waypoint", "detail": "区域名称不能直接作为传送锚点；保留相对方位和锚点待核验状态"})
    return {"status": "rejected" if issues else "pending_human_review", "issues": issues, "execution_allowed": False}


def build_grounding(project, output, waypoint_path, retry_path=None):
    import cv2
    import numpy as np
    import importlib.metadata
    from rapidocr_onnxruntime import RapidOCR
    import rapidocr_onnxruntime
    points = catalog_points(json.loads(waypoint_path.read_text(encoding="utf-8-sig")))
    source = project["sources"][0]
    retry_data = None
    if retry_path:
        retry_data = json.loads(retry_path.read_text(encoding="utf-8-sig"))
        if not source.get("sha256") or retry_data.get("video_sha256") != source["sha256"]:
            raise ValueError("第二次转写与视频 hash 不匹配，拒绝混用来源")
        for row in retry_data["segments"]:
            if not 0 <= row["start"] <= row["end"] <= source["duration_s"] or not isinstance(row["text"], str):
                raise ValueError("第二次转写包含无效时刻或文字")
            for word in row.get("words", []):
                if not row["start"] - .05 <= word["start"] <= word["end"] <= row["end"] + .05 or not isinstance(word["word"], str):
                    raise ValueError("第二次转写词级时间超出所属语句")
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    model_root = Path(rapidocr_onnxruntime.__file__).parent
    raw = {"engine": "rapidocr_onnxruntime", "version": importlib.metadata.version("rapidocr_onnxruntime"),
           "models": {p.name: sha256(p) for p in sorted(model_root.rglob("*.onnx"))}, "frames": []}
    frames = []
    for ev in project["evidence_index"]:
        if ev["kind"] != "frame":
            continue
        image = cv2.imdecode(np.fromfile(output / ev["path"], dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("无法读取证据图片: " + ev["path"])
        rows, timings = engine(image)
        rows = rows or []
        h, w = image.shape[:2]
        raw["frames"].append({"evidence_id": ev["id"], "frame_sha256": ev["sha256"], "width": w, "height": h, "rows": rows})
        frames.append(classify_frame(ev["id"], rows, w, h, region_terms(points)))
        print(json.dumps({"stage": "ocr", "frame": ev["id"], "rows": len(rows)}), flush=True)
    artifact = lambda rel: {"path": rel, "sha256": sha256(output / rel)}
    dump(raw, output / "evidence/ocr_raw.json")
    dump(json.loads(waypoint_path.read_text(encoding="utf-8-sig")), output / "evidence/waypoint_catalog.json")
    retry_ref = None
    if retry_data:
        dump(retry_data, output / "evidence/asr_retry.json")
        retry_ref = artifact("evidence/asr_retry.json")
    vocabulary = region_terms(points) | set(ANCHOR_TYPES)
    project["schema_version"] = "1.2.0"
    project["grounding"] = {"version": "1.0.0", "ocr_artifact": artifact("evidence/ocr_raw.json"),
        "catalog_artifact": artifact("evidence/waypoint_catalog.json"), "retry_artifact": retry_ref,
        "frames": frames, "transcripts": compare_transcripts(project["evidence_index"], (retry_data or {}).get("segments", []), frames, vocabulary),
        "anchors": [anchor_candidates(f, points) for f in frames],
        "plan_review": {"status": "pending_human_review", "issues": [], "execution_allowed": False}}
    dump(project["grounding"], output / "grounding.json")
    return project["grounding"]


def validate_grounding(project, root=None):
    g = project["grounding"]; errors = []; evidence = {e["id"]: e for e in project["evidence_index"]}
    def read_artifact(ref):
        if root is None or ref is None:
            return None
        base = Path(root).resolve(); path = (base / ref["path"]).resolve()
        if not path.is_relative_to(base) or Path(ref["path"]).is_absolute():
            errors.append("grounding artifact path escapes output directory"); return None
        if not path.is_file() or sha256(path) != ref["sha256"]:
            errors.append("grounding artifact missing or sha256 mismatch: " + ref["path"]); return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            errors.append("invalid grounding JSON artifact"); return None
    raw = read_artifact(g["ocr_artifact"]); cat = read_artifact(g["catalog_artifact"]); retry = read_artifact(g["retry_artifact"])
    frame_ids = [f["evidence_id"] for f in g["frames"]]
    if len(set(frame_ids)) != len(frame_ids) or set(frame_ids) != {e["id"] for e in evidence.values() if e["kind"] == "frame"}:
        errors.append("grounding frame ids do not match source frames")
    transcript_ids = [r["evidence_id"] for r in g["transcripts"]]
    if len(set(transcript_ids)) != len(transcript_ids) or set(transcript_ids) != {e["id"] for e in evidence.values() if e["kind"] == "asr"}:
        errors.append("grounding transcript ids do not match original ASR")
    anchor_ids = [a["frame_id"] for a in g["anchors"]]
    if len(set(anchor_ids)) != len(anchor_ids) or set(anchor_ids) != set(frame_ids):
        errors.append("grounding anchor frame ids do not match source frames")
    text_rows = {}
    for frame in g["frames"]:
        for row in frame["rows"]:
            if row["id"] in text_rows:
                errors.append("grounding duplicate OCR text id")
            text_rows[row["id"]] = (frame["evidence_id"], row)
            x1, y1, x2, y2 = row["bbox"]
            if not x1 <= x2 or not y1 <= y2 or row["eligible"] != (row["role"] in ELIGIBLE):
                errors.append("grounding OCR bbox or role/eligibility is invalid")
    for anchor in g["anchors"]:
        for text_id in anchor["text_ids"] + anchor["region_text_ids"]:
            if text_rows.get(text_id, (None,))[0] != anchor["frame_id"]:
                errors.append("grounding anchor text belongs to another frame")
    for row in g["transcripts"]:
        original = evidence.get(row["evidence_id"])
        if not original or original["kind"] != "asr" or row["original"] != original["text"]:
            errors.append("grounding transcript overwrote or lost the original")
            continue
        for support in row["corroborated_terms"] + row["lexical_candidates"]:
            fid = support["frame_id"]; text_id = support["text_id"]
            target = text_rows.get(text_id)
            if not target or target[0] != fid or not target[1]["eligible"] or fid not in evidence:
                errors.append("grounding transcript support has invalid frame/text reference")
            elif not original["time"]["start_s"] - 3 <= evidence[fid]["time"]["start_s"] <= original["time"]["end_s"] + 3:
                errors.append("grounding transcript support is outside its time window")
    if retry and retry.get("video_sha256") != project["sources"][0]["sha256"]:
        errors.append("grounding retranscript belongs to a different video")
    if raw and cat:
        try:
            points = catalog_points(cat)
            expected_frames = [classify_frame(f["evidence_id"], f["rows"], f["width"], f["height"], region_terms(points)) for f in raw["frames"]]
            if any(f["frame_sha256"] != evidence.get(f["evidence_id"], {}).get("sha256") for f in raw["frames"]):
                errors.append("OCR source frame hash mismatch")
            if expected_frames != g["frames"]:
                errors.append("grounding OCR classification differs from raw artifact")
            if [anchor_candidates(f, points) for f in expected_frames] != g["anchors"]:
                errors.append("grounding waypoint candidates differ from catalog/evidence")
            expected_asr = compare_transcripts(project["evidence_index"], (retry or {}).get("segments", []), expected_frames, region_terms(points) | set(ANCHOR_TYPES))
            if expected_asr != g["transcripts"]:
                errors.append("grounding transcript alternatives differ from evidence")
        except (KeyError, TypeError, ValueError):
            errors.append("malformed grounding source artifact")
    if review_plan(project) != g["plan_review"]:
        errors.append("grounding semantic review does not match the plan")
    return errors


def transcribe_audio(video, audio, model_dir, output, start, end, domain_prompt=False):
    """Run a local second opinion; it never replaces an imported transcript."""
    import time
    import importlib.metadata
    from faster_whisper import WhisperModel
    if not model_dir.is_dir() or not (model_dir / "model.bin").is_file():
        raise ValueError("需要已下载的本地 Whisper 模型目录，不自动下载模型")
    if not 0 <= start < end:
        raise ValueError("invalid transcription clip")
    if output.exists():
        raise FileExistsError("拒绝覆盖已有转写: " + str(output))
    prompt = "原神攻略。传送锚点，七天神像，秘境，蒙德，纳塔，回声之子，硫晶支脉，隆崛坡，坚岩隘谷，涌流地。" if domain_prompt else None
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=4, num_workers=1)
    started = time.monotonic()
    segments, info = model.transcribe(str(audio), language="zh", beam_size=5 if domain_prompt else 3,
        initial_prompt=prompt, condition_on_previous_text=False, clip_timestamps=[start, end], word_timestamps=True)
    rows = [{"start": s.start, "end": s.end, "text": s.text, "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob,
             "words": [{"start": w.start, "end": w.end, "word": w.word, "probability": w.probability} for w in (s.words or [])]} for s in segments]
    result = {"method": "faster_whisper_cpu_int8", "library_version": importlib.metadata.version("faster-whisper"),
              "model_path": str(model_dir.resolve()), "model_sha256": sha256(model_dir / "model.bin"),
              "video_sha256": sha256(video), "audio_path": str(audio.resolve()), "audio_sha256": sha256(audio),
              "audio_video_offset_s": 0, "alignment_note": "调用方提供同起点的视频和音轨；不自动校准偏移",
              "clip": [start, end], "initial_prompt": prompt, "beam_size": 5 if domain_prompt else 3,
              "condition_on_previous_text": False, "word_timestamps": True, "segments": rows, "elapsed_s": round(time.monotonic() - started, 3)}
    output.parent.mkdir(parents=True, exist_ok=True)
    dump(result, output)
    return result
