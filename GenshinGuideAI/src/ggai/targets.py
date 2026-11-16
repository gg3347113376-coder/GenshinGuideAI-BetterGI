"""Bind plan actions to typed evidence targets, never to invented coordinates."""
from __future__ import annotations

import hashlib
import json
import re

ALLOWED_KINDS = {
    "teleport": {"waypoint", "statue", "domain"}, "move_to": {"location", "waypoint", "statue", "domain", "chest", "object"},
    "sprint": {"location"}, "climb": {"location"}, "fight": {"enemy"},
    "interact": {"waypoint", "statue", "domain", "chest", "object"}, "dialogue_choice": {"object"},
    "wait": {"unknown"}, "unknown": {"unknown", "location", "waypoint", "object"},
}


def fingerprint(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def evidence_units(project, include_excluded=False):
    evidence = {e["id"]: e for e in project["evidence_index"]}
    units = []
    for t in project["grounding"]["transcripts"]:
        ev = evidence[t["evidence_id"]]
        units.append({"id": t["evidence_id"] + ":original", "evidence_id": t["evidence_id"],
                      "basis": "asr_original_unverified", "text": t["original"], "time": ev["time"]})
        if t["alternative"] and t["status"] != "context_only":
            units.append({"id": t["evidence_id"] + ":retry", "evidence_id": t["evidence_id"],
                          "basis": "asr_alternative_unverified", "text": t["alternative"], "time": ev["time"]})
    for frame in project["grounding"]["frames"]:
        for row in frame["rows"]:
            if not include_excluded and not row["eligible"]:
                continue
            units.append({"id": row["id"], "evidence_id": frame["evidence_id"], "basis": "ocr_unverified",
                          "text": row["text"], "position": [round(x, 3) for x in row["bbox"]],
                          "role_hint": row["role"], "confidence": round(row["confidence"], 3),
                          "time": evidence[frame["evidence_id"]]["time"]})
    return units


def build_registry(project):
    units = evidence_units(project)
    lookup = {u["id"]: u for u in units}
    entities = []
    def add(kind, role, label, selected, resolution="unresolved", candidates=(), references=()):
        if not selected:
            return None
        selected = list(dict.fromkeys(u["id"] for u in selected))
        entity = {"id": f"target_{len(entities) + 1:03d}", "kind": kind, "role": role,
                  "label": label, "resolution": resolution, "unit_ids": selected,
                  "evidence_ids": list(dict.fromkeys(lookup[u]["evidence_id"] for u in selected)),
                  "candidate_points": list(candidates), "reference_target_ids": list(references),
                  "verified_identity": None, "coordinates": None, "current_player_unlocked": "unknown"}
        entities.append(entity)
        return entity
    regions = {}
    for frame in project["grounding"]["frames"]:
        for row in frame["rows"]:
            if row["role"] == "selected_region" and row["text"] not in regions:
                regions[row["text"]] = add("region", "selected_region", row["text"], [lookup[row["id"]]], "descriptive")
    for t in project["grounding"]["transcripts"]:
        for c in t["lexical_candidates"]:
            name = c["candidate"]
            if name not in regions and lookup[c["text_id"]].get("role_hint") == "map_region":
                regions[name] = add("region", "spelling_candidate", name + "（拼字候选）",
                                    [lookup[t["evidence_id"] + ":original"], lookup[c["text_id"]]], "candidate")
    for anchor in project["grounding"]["anchors"]:
        if not anchor["selected_panel_visible"]:
            continue
        selected = [lookup[i] for i in anchor["text_ids"] + anchor["region_text_ids"] if i in lookup]
        region = "、".join(anchor["region_labels"]) or "区域未知"
        points = [{"scene_id": p["scene_id"], "id": p["id"]} for p in anchor["candidates"]]
        # A type/region match is not a physical waypoint identity, even with one candidate.
        kind = "waypoint" if anchor["anchor_type"] == "TeleportWaypoint" else ("statue" if anchor["anchor_type"] == "Goddess" else "domain")
        add(kind, "map_selection", region + "的传送点（具体身份待核验）", selected,
            "ambiguous" if len(points) > 1 else "unresolved", points)
    anchor_units = [u for u in units if any(w in u["text"] for w in ("锚点", "传送点", "传送某点"))]
    unlock = [u for u in anchor_units if re.search(r"解锁|激活", u["text"]) and u.get("role_hint") in ("tutorial", "quest_tracker", "subtitle", "interaction_prompt")]
    if unlock:
        add("waypoint", "world_interaction", "解锁提示所指的传送锚点（身份未知）", unlock, "type_only")
    spoken_ids = {u["evidence_id"] for u in anchor_units if u["basis"].startswith("asr") and "隐藏" not in u["text"]}
    start_ids = {u["evidence_id"] for u in units if u["evidence_id"] in spoken_ids and
                 u["basis"].startswith("asr") and re.search(r"回到|来到|传送到|传送至|先传送|传送过[去来]", u["text"])}
    spoken = [u for u in units if u["basis"].startswith("asr") and u["evidence_id"] in start_ids]
    if spoken:
        refs = [e["id"] for e in regions.values() if e and any(eid in e["evidence_ids"] for eid in [u["evidence_id"] for u in spoken])]
        add("waypoint", "narrated_start", "解说中的起点传送锚点（名称与身份待核验）", spoken, "type_only", references=refs)
    hidden = [u for u in anchor_units if u["basis"].startswith("asr") and "隐藏" in u["text"]]
    if hidden:
        add("waypoint", "narrated_goal", "解说提到的隐藏锚点（尚未定位）", hidden)
    originals = [u for u in units if u["basis"] == "asr_original_unverified"]
    chests = [u for u in originals if "宝箱" in u["text"] or "开箱" in u["text"]]
    add("chest", "narrated_object", "解说中的宝箱（具体对象待定位）", chests, "descriptive")
    enemies = [u for u in originals if re.search(r"把.{0,8}怪.{0,5}清|清怪|击败.{0,8}(?:敌|怪)|消灭.{0,8}(?:敌|怪)", u["text"])]
    add("enemy", "narrated_object", "解说要求清理的怪物（种类待识别）", enemies, "descriptive")
    for u in originals:
        if re.search(r"方向|树下|底下|下方|朝.{0,10}走|(?:到|前往).{0,10}位置", u["text"]):
            add("location", "relative_location", "原文“" + u["text"].strip() + "”所指位置（待定位/辨认）", [u])
    for u in units:
        if u.get("role_hint") == "interaction_prompt" and any(u["text"] in a["text"] for a in originals):
            add("object", "visible_interaction", u["text"], [u], "descriptive")
    add("unknown", "unresolved", "尚未识别的目标", units[:1])
    return {"version": "1.0.0", "entities": entities}


def action_label(action_id, target):
    if action_id == "interact":
        if target.get("kind") == "chest":
            return "开启宝箱"
        if target.get("role") == "world_interaction":
            return "解锁传送锚点"
        return "与目标交互"
    return {"teleport": "锚点传送", "move_to": "前往目标", "fight": "清理敌人",
            "sprint": "冲刺", "climb": "攀爬", "dialogue_choice": "选择对话",
            "wait": "等待条件满足", "unknown": "待明确动作"}[action_id]


def goal_text(target, action_names):
    return "目标：" + target["label"] + "；当前片段：" + " → ".join(action_names)


def binding_issues(project):
    entities = {e["id"]: e for e in project["target_registry"]["entities"]}
    issues = []
    goal = entities.get(project["task_plan"].get("goal_target_ref"))
    if goal is None:
        issues.append({"step_id": "plan", "code": "unknown_goal_target", "detail": "最终任务目标必须绑定到证据实体"})
    elif project["task_plan"]["goal"] != goal_text(goal, [action_label(s["action_id"], entities.get(s.get("target_ref"), {})) for s in project["task_plan"]["steps"]]):
        issues.append({"step_id": "plan", "code": "goal_label_mismatch", "detail": "最终任务说明与绑定目标及动作链不一致"})
    elif project["task_plan"]["steps"]:
        terminal = entities.get(project["task_plan"]["steps"][-1].get("target_ref"))
        if terminal and goal["kind"] != terminal["kind"] and goal["role"] != "narrated_goal":
            issues.append({"step_id": "plan", "code": "goal_target_mismatch", "detail": "最终目标类型与步骤终点不符，也不是解说明示的后续目标"})
    for s in project["task_plan"]["steps"]:
        target = entities.get(s.get("target_ref"))
        if target is None:
            issues.append({"step_id": s["id"], "code": "unknown_target_id", "detail": "目标 ID 不在证据注册表"})
            continue
        if target["kind"] not in ALLOWED_KINDS[s["action_id"]]:
            issues.append({"step_id": s["id"], "code": "target_type_mismatch", "detail": s["action_id"] + " 不能绑定 " + target["kind"]})
        if "target_label" in s["params"] and s["params"]["target_label"] != target["label"]:
            issues.append({"step_id": s["id"], "code": "target_label_mismatch", "detail": "动作参数与绑定实体不一致"})
        if not set(s["evidence_ids"]) & set(target["evidence_ids"]):
            issues.append({"step_id": s["id"], "code": "target_without_step_evidence", "detail": "步骤未引用支持其绑定目标的证据"})
        if s["action_id"] == "teleport" and target["role"] == "narrated_goal":
            issues.append({"step_id": s["id"], "code": "unlocalized_destination", "detail": "探索的最终锚点尚未定位，不能把它直接当作出发传送点"})
    return issues


def object_claim_issues(project):
    """A new enemy category needs local text support; fuzzy ASR cannot provide it."""
    units = evidence_units(project)
    issues = []
    for step in project["task_plan"]["steps"]:
        text = " ".join([step["title"], step["intent"], step["params"].get("target_label", "")])
        # Quoting an unresolved source word does not assert that word's category.
        assertion = re.sub("“[^”]*”", "", text)
        if not any(word in assertion for word in ("怪物", "敌人", "怪兽", "魔物", "清怪", "击败")):
            continue
        local = [u for u in units if u["evidence_id"] in step.get("instruction_evidence_ids", [])
                 and u.get("role_hint") != "map_region"]
        explicit = r"怪物|敌人|怪兽|魔物|丘丘|史莱姆|清怪|把.{0,8}怪.{0,5}清|(?:击败|消灭|清理).{0,8}(?:敌|怪)"
        if not any(re.search(explicit, u["text"]) for u in local):
            issues.append({"step_id": step["id"], "code": "unproven_object_category",
                "detail": "本步指令没有直接的敌人类别依据；模糊转写只能保留原词所指位置，不能补成怪物"})
    return issues


def teleport_instruction_ids(project, target=None):
    targets = [target] if target else project["target_registry"]["entities"]
    start_refs = {eid for item in targets if item.get("role") == "narrated_start" for eid in item["evidence_ids"]}
    result = set()
    for unit in evidence_units(project):
        if unit.get("role_hint") == "map_region":
            continue
        explicit = re.search(r"传送到|传送至|先传送|传送过[去来]|点[击选].{0,16}(?:传送|锚点|神像|秘境)", unit["text"])
        start = unit["evidence_id"] in start_refs and re.search(r"回到|来到", unit["text"])
        if explicit or start:
            result.add(unit["evidence_id"])
    return result


def teleport_instruction_issues(project):
    targets = {t["id"]: t for t in project["target_registry"]["entities"]}
    issues = []
    for step in project["task_plan"]["steps"]:
        if step["action_id"] != "teleport":
            continue
        target = targets.get(step.get("target_ref"), {})
        claims = [re.sub("“[^”]*”", "", value) for value in
                  (step["title"], step["intent"], step["params"].get("target_label", ""))]
        uncertain = r"唯一.{0,10}(?:待核验|待确认|未知|未确认)|(?:待核验|待确认|未知|未确认).{0,10}唯一"
        if target.get("verified_identity") is None and any("唯一" in claim and not re.search(uncertain, claim) for claim in claims):
            issues.append({"step_id": step["id"], "code": "unproven_waypoint_identity",
                "detail": "候选锚点尚无核实身份，不能把区域名称或未知对象写成唯一锚点"})
        instruction_ids = teleport_instruction_ids(project, target)
        if target.get("role") == "world_interaction" or not set(step.get("instruction_evidence_ids", [])) & instruction_ids:
            issues.append({"step_id": step["id"], "code": "unsupported_teleport_instruction",
                "detail": "本步没有传送指令；靠近或解锁提示不能作为地图传送依据"})
    return issues


def reviewed_payload(project):
    return {"plan": project["task_plan"], "targets": project["target_registry"],
            "source_units": evidence_units(project, include_excluded=True),
            "evidence_index": project["evidence_index"], "sources": project["sources"]}


def goal_candidates(project):
    entities = project["target_registry"]["entities"]
    explicit = [t["id"] for t in entities if t["role"] == "narrated_goal"]
    return explicit or [t["id"] for t in entities if t["kind"] != "region"]


def sequence_issues(project, include_frames=True):
    issues = []
    def issue(sid, code, detail):
        issues.append({"step_id": sid, "code": code, "detail": detail})
    if project["task_plan"].get("goal_target_ref") not in goal_candidates(project):
        issue("plan", "goal_role_mismatch", "已登记的总目标不能被起点或过程位置替换；片段可以只覆盖途中步骤")
    evidence = {e["id"]: e for e in project["evidence_index"]}
    used = {}
    latest = -1
    for step in project["task_plan"]["steps"]:
        refs = step.get("instruction_evidence_ids", [])
        if not refs or any(eid not in evidence or eid not in step["evidence_ids"] for eid in refs):
            issue(step["id"], "missing_instruction_evidence", "动作需要独立记录有效的指令证据，不能用对象识别证据代替")
            continue
        key = (step["action_id"], step["target_ref"])
        if set(refs) <= used.get(key, set()):
            issue(step["id"], "repeated_instruction", "重复执行同一动作需要新的指令依据；起点说明不能再次充当返回指令")
        used.setdefault(key, set()).update(refs)
        times = [evidence[eid]["time"]["start_s"] for eid in refs if include_frames or evidence[eid]["kind"] == "asr"]
        if times:
            # shortcut: one ASR segment may contain several actions; split it before validating such routes.
            current = max(times)
            if current < latest:
                issue(step["id"], "instruction_order", "步骤回用了更早的解说指令，行动顺序与当前片段的时间顺序不符")
            latest = max(latest, current)
    return issues
