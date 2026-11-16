"""Evidence-linked task plans. This module never creates executor commands."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]


def catalog() -> dict:
    return json.loads((ROOT / "schema/action_catalog.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(value: dict, path: Path) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def blockers_for(action: dict, params: dict, dependencies: list[dict]) -> list[dict]:
    blockers = []
    for field in action["required_for_execution"]:
        if params.get(field) in (None, "", "unknown"):
            blockers.append({"code": "missing_parameter", "detail": f"{field}: 尚无已核对的参数"})
    if action["binding"]["status"] == "not_implemented":
        blockers.append({"code": "unsupported_action", "detail": "此动作尚无满足语义的执行实现"})
    if any(step["status"] == "blocked" for step in dependencies):
        blockers.append({"code": "dependency_blocked", "detail": "前置任务尚未具备执行条件"})
    return blockers


def order_linear_draft(project: dict, draft: dict) -> tuple[dict, dict]:
    steps = draft["steps"]
    original_ids = [s["id"] for s in steps]
    receipt = {"status": "unchanged", "before": original_ids, "after": original_ids, "windows": []}
    if len(steps) < 2:
        return draft, receipt
    if len(set(original_ids)) != len(steps) or any(s["depends_on"] != ([] if i == 0 else [steps[i - 1]["id"]]) for i, s in enumerate(steps)):
        return draft, {**receipt, "status": "needs_review", "reason": "依赖不是单一线性动作链"}
    evidence = {e["id"]: e for e in project["evidence_index"]}
    refs = [eid for step in steps for eid in step["evidence_ids"]]
    if any(not step["evidence_ids"] for step in steps) or any(eid not in evidence for eid in refs):
        return draft, {**receipt, "status": "needs_review", "reason": "缺少有效的动作指令证据"}
    if len({evidence[eid]["source_id"] for eid in refs}) != 1:
        return draft, {**receipt, "status": "needs_review", "reason": "不同视频的时间不能直接比较"}
    text = " ".join(e["text"] for e in project["evidence_index"] if e["kind"] == "asr")
    if any(word in text for word in ("如果", "否则", "或者", "假如", "刚才", "之前", "回顾", "倒叙")):
        return draft, {**receipt, "status": "needs_review", "reason": "存在条件或回顾提示，不能当作顺叙自动重排"}
    windows = {step["id"]: (min(evidence[eid]["time"]["start_s"] for eid in step["evidence_ids"]),
                            max(evidence[eid]["time"]["end_s"] for eid in step["evidence_ids"])) for step in steps}
    receipt["windows"] = [{"step_id": step["id"], "instruction_evidence_ids": step["evidence_ids"],
        "start_s": windows[step["id"]][0], "end_s": windows[step["id"]][1]} for step in steps]
    ordered = sorted(steps, key=lambda step: windows[step["id"]][0])
    if [step["id"] for step in ordered] == original_ids:
        return draft, receipt
    if any(windows[a["id"]][1] > windows[b["id"]][0] for a, b in zip(ordered, ordered[1:])):
        return draft, {**receipt, "status": "needs_review", "reason": "指令时间区间重叠，顺序仍需辨认"}
    # Keep source step IDs; only sequence and predecessor links follow disjoint instruction windows.
    fixed = {**draft, "steps": [{**step, "depends_on": [] if i == 0 else [ordered[i - 1]["id"]]} for i, step in enumerate(ordered)]}
    return fixed, {**receipt, "status": "reordered", "after": [s["id"] for s in ordered],
        "reason": "依据同一顺叙片段中不重叠的指令时间重排；原模型步骤标识和内容保留"}


def make_plan(project: dict, draft: dict, analysis_ids: list[str]) -> dict:
    from .protocol import add_event
    cat = catalog()
    actions = {a["id"]: a for a in cat["actions"]}
    evidence = {e["id"]: e for e in project["evidence_index"]}
    targets = {e["id"]: e for e in project.get("target_registry", {}).get("entities", [])}
    goal = draft.get("goal", "")
    if targets:
        from .targets import goal_text, action_label
        if draft.get("goal_target_id") not in targets:
            raise ValueError("最终目标 ID 未登记")
        goal = goal_text(targets[draft["goal_target_id"]], [action_label(c["action_id"], targets.get(c.get("target_id"), {})) for c in draft["steps"]])
    plan = {"id": project["project"]["id"] + "_plan", "catalog_version": cat["schema_version"],
            "goal": goal, "mode": "plan_only", "execution_allowed": False,
            "status": "needs_review", "analysis_run_ids": analysis_ids, "steps": [],
            "uncertainties": draft["uncertainties"],
            "confidence_note": "confidence 是模型自评分，未经过准确率校准；所有步骤待复核，均未实机执行。"}
    if targets:
        plan["goal_target_ref"] = draft["goal_target_id"]
    if targets and any(c.get("target_id") not in targets for c in draft["steps"]):
        raise ValueError("计划引用了未登记的目标 ID")
    seen = {}
    for candidate in draft["steps"]:
        action = actions[candidate["action_id"]]
        if targets:
            target = targets[candidate["target_id"]]
            instruction_refs = list(candidate["evidence_ids"])
            # Bind the displayed assertions too; free-form titles can reintroduce invented names.
            candidate = {**candidate, "title": action_label(action["id"], target) + "：" + target["label"],
                "intent": action_label(action["id"], target) + "；以绑定目标的来源为依据，实际身份和执行条件仍待核验",
                "expected_result": "对绑定目标检查：" + "；".join(cat["checks"][key] for key in action["postconditions"]),
                "evidence_ids": list(dict.fromkeys(candidate["evidence_ids"] + target["evidence_ids"]))}
            if action["id"] == "teleport" and not candidate["uncertainties"]:
                candidate["uncertainties"] = []
                if target["verified_identity"] is None:
                    candidate["uncertainties"].append("目标登记：具体锚点身份尚未核验")
                if target["coordinates"] is None:
                    candidate["uncertainties"].append("目标登记：锚点坐标尚未核验")
                if target["current_player_unlocked"] == "unknown":
                    candidate["uncertainties"].append("目标登记：当前玩家的解锁状态未知")
        sid = candidate["id"]
        if sid in seen or any(dep not in seen for dep in candidate["depends_on"]):
            raise ValueError("步骤 ID 重复，或依赖不是前面的步骤")
        refs = candidate["evidence_ids"]
        if not refs or len(set(refs)) != len(refs) or any(eid not in evidence for eid in refs):
            raise ValueError(f"{sid}: 引用了不存在或重复的证据")
        source_ids = {evidence[eid]["source_id"] for eid in refs}
        if len(source_ids) != 1:
            raise ValueError("单步证据必须来自同一个视频")
        params = {}
        for key in action["parameter_schema"]["properties"]:
            if key == "target_label" and targets:
                params[key] = targets[candidate["target_id"]]["label"]
            elif key in ("target_label", "target_text", "option_text", "condition"):
                params[key] = candidate[key]
            elif key in ("layer", "coordinate_system"):
                params[key] = "unknown"
            else:
                params[key] = None
        jsonschema.Draft202012Validator(action["parameter_schema"]).validate(params)
        checks = lambda ids: [{"id": key, "description": cat["checks"][key], "status": "not_checked"} for key in ids]
        blockers = blockers_for(action, params, [seen[d] for d in candidate["depends_on"]])
        event_id = project["project"]["id"] + "_" + sid
        step = {"id": sid, "action_id": action["id"], "title": candidate["title"],
                "intent": candidate["intent"], "params": params, "depends_on": candidate["depends_on"],
                "source_event_ids": [event_id], "evidence_ids": refs,
                "preconditions": checks(action["preconditions"]),
                "expected_result": {"text": candidate["expected_result"], "checks": checks(action["postconditions"])},
                "observed_result": {"status": "not_executed", "evidence_ids": []},
                "status": "blocked" if blockers else "needs_review", "blockers": blockers,
                "uncertainties": candidate["uncertainties"], "confidence": candidate["confidence"],
                "timeout_s": action["timeout_s"], "max_retries": 0, "review": {"status": "pending"}}
        if targets:
            step["target_ref"] = candidate["target_id"]
            step["instruction_evidence_ids"] = instruction_refs
        selected = [evidence[eid] for eid in refs]
        add_event(project, {
            "id": event_id, "source_id": next(iter(source_ids)), "segment_id": project["segments"][0]["id"],
            "video_time": {"start_s": min(e["time"]["start_s"] for e in selected),
                           "end_s": max(e["time"]["end_s"] for e in selected), "precision": "segment"},
            "actor": {"kind": "player", "name": "", "confidence": 0},
            "action": {"type": action["legacy_event_type"], "params": params, "method": "inferred",
                       "notes": "由攻略证据推断的待办；不是已观测到的用户游戏操作"},
            "position": {"map": {"x": None, "y": None, "layer": "unknown", "method": "unknown", "confidence": 0}},
            "preconditions": [c["description"] for c in step["preconditions"]],
            "expected_result": {"text": candidate["expected_result"], "checks": action["postconditions"]},
            "observed_result": {"text": "未执行", "checks": []}, "state_status": "inferred",
            "confidence": candidate["confidence"],
            "evidence": [{"kind": e["kind"], "t_s": e["time"]["start_s"], "path": e["path"],
                          "text": e["text"], "note": "evidence_id=" + e["id"]} for e in selected],
        })
        seen[sid] = step
        plan["steps"].append(step)
    project["task_plan"] = plan
    return plan


def validate_links(project: dict, artifact_root: Path | None = None) -> list[str]:
    """Run after JSON Schema validation; also verify physical artifacts when a root is supplied."""
    errors = []
    cat = catalog()
    actions = {a["id"]: a for a in cat["actions"]}
    def index(items, label):
        found = {x["id"]: x for x in items}
        if len(found) != len(items):
            errors.append(f"{label}: duplicate id")
        return found
    sources = index(project["sources"], "sources")
    segments = index(project["segments"], "segments")
    evidence = index(project["evidence_index"], "evidence")
    events = index(project["events"], "events")
    traces = index(project["analysis_runs"], "analysis_runs")
    steps = index(project["task_plan"]["steps"], "steps")
    checked_files = set()
    def verify_file(relative, digest, label):
        if artifact_root is None:
            return
        base = Path(artifact_root).resolve()
        path = (base / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(base):
            errors.append(f"{label}: artifact path escapes output directory")
            return
        key = (path, digest)
        if key in checked_files:
            return
        checked_files.add(key)
        if not path.is_file():
            errors.append(f"{label}: missing artifact {relative}")
        elif sha256(path) != digest:
            errors.append(f"{label}: sha256 mismatch {relative}")
    for segment in segments.values():
        source = sources.get(segment["source_id"])
        if not source or not 0 <= segment["start_s"] <= segment["end_s"] <= source["duration_s"]:
            errors.append(f"segment {segment['id']}: invalid source/time")
    for ev in evidence.values():
        source = sources.get(ev["source_id"])
        time = ev["time"]
        if not source or not 0 <= time["start_s"] <= time["end_s"] <= source["duration_s"]:
            errors.append(f"evidence {ev['id']}: invalid source/time")
        verify_file(ev["path"], ev["sha256"], ev["id"])
        if artifact_root is not None and ev["kind"] == "asr":
            path = (Path(artifact_root) / ev["path"]).resolve()
            if path.is_relative_to(Path(artifact_root).resolve()) and path.is_file():
                try:
                    rows = json.loads(path.read_text(encoding="utf-8"))["segments"]
                    matches = [r for r in rows if r["id"] == ev["id"]]
                    if len(matches) != 1 or any(matches[0].get(k) != value for k, value in {
                        "text": ev["text"], "start_s": time["start_s"], "end_s": time["end_s"]}.items()):
                        errors.append(f"{ev['id']}: transcript evidence differs from original artifact")
                except (ValueError, KeyError, TypeError):
                    errors.append(f"{ev['id']}: invalid transcript artifact")
    for trace in traces.values():
        for key in ("request", "response"):
            verify_file(trace[key + "_path"], trace[key + "_sha256"], trace["id"])
        if any(eid not in evidence for eid in trace["evidence_ids"]):
            errors.append(f"{trace['id']}: unknown evidence id")
    analysis_ids = project["task_plan"]["analysis_run_ids"]
    if any(rid not in traces for rid in analysis_ids) or not any(
            traces.get(rid, {}).get("stage") == "task_understanding" for rid in analysis_ids):
        errors.append("plan: missing task understanding trace")
    for event in events.values():
        source = sources.get(event["source_id"])
        time = event["video_time"]
        if not source or not 0 <= time["start_s"] <= time["end_s"] <= source["duration_s"]:
            errors.append(f"event {event['id']}: invalid source/time")
        segment = segments.get(event.get("segment_id"))
        if segment is None or segment["source_id"] != event["source_id"]:
            errors.append(f"event {event['id']}: invalid segment")
    previous = {}
    for step in project["task_plan"]["steps"]:
        sid = step["id"]
        action = actions[step["action_id"]]
        for err in jsonschema.Draft202012Validator(action["parameter_schema"]).iter_errors(step["params"]):
            errors.append(f"{sid}/params: {err.message}")
        if any(dep not in previous for dep in step["depends_on"]):
            errors.append(f"{sid}: dependency must reference a preceding step")
        selected = [evidence[eid] for eid in step["evidence_ids"] if eid in evidence]
        if len(selected) != len(step["evidence_ids"]):
            errors.append(f"{sid}: unknown evidence id")
        for eid in step["source_event_ids"]:
            event = events.get(eid)
            if event is None:
                errors.append(f"{sid}: unknown source event {eid}")
                continue
            if event["action"]["type"] != action["legacy_event_type"] or event["action"].get("params") != step["params"]:
                errors.append(f"{sid}: event/action mismatch")
            for ev in selected:
                if ev["source_id"] != event["source_id"] or not (
                    event["video_time"]["start_s"] <= ev["time"]["start_s"] <= ev["time"]["end_s"] <= event["video_time"]["end_s"]):
                    errors.append(f"{sid}: evidence outside event source/time")
        for field, expected in ((step["preconditions"], action["preconditions"]),
                                (step["expected_result"]["checks"], action["postconditions"])):
            if [c["id"] for c in field] != expected or any(c["description"] != cat["checks"][c["id"]] for c in field):
                errors.append(f"{sid}: catalog checks missing or modified")
        expected_blockers = blockers_for(action, step["params"], [previous[d] for d in step["depends_on"] if d in previous])
        if step["blockers"] != expected_blockers or step["status"] != ("blocked" if expected_blockers else "needs_review"):
            errors.append(f"{sid}: blockers/status do not match missing capabilities")
        if step["timeout_s"] != action["timeout_s"]:
            errors.append(f"{sid}: timeout differs from catalog")
        previous[sid] = step
    return errors


def audit_bindings(projects_root: Path) -> list[dict]:
    rows = []
    for action in catalog()["actions"]:
        binding = action["binding"]
        path = projects_root / binding["path"] if binding["path"] else None
        found = bool(path and path.is_file() and binding["symbol"] in path.read_text(encoding="utf-8-sig"))
        rows.append({"action_id": action["id"], "path": binding["path"], "symbol_found": found,
                     "source_sha256": sha256(path) if path and path.is_file() else None,
                     "adapter_connected": False, "live_verified": False})
    return rows
