"""协议 v1：加载、校验、构造与摘要。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "project_v1.schema.json"


def load_schema(version: str = "1.0.0") -> dict:
    if version not in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
        raise ValueError(f"不支持的协议版本: {version}")
    path = SCHEMA_PATH if version == "1.0.0" else SCHEMA_PATH.with_name("project_v" + version.rsplit(".", 1)[0].replace(".", "_") + ".schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(project: dict, artifact_root: Path | None = None) -> list[str]:
    """返回错误列表；空列表表示通过。"""
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("需要 jsonschema：python -m pip install jsonschema") from exc
    if not isinstance(project, dict):
        return ["项目必须是 JSON 对象"]
    version = project.get("schema_version", "1.0.0")
    try:
        validator = jsonschema.Draft202012Validator(load_schema(version))
    except ValueError as exc:
        return [str(exc)]
    errors = []
    for err in sorted(validator.iter_errors(project), key=lambda e: "/".join(map(str, e.absolute_path))):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path}: {err.message}")
    if not errors and version in ("1.1.0", "1.2.0", "1.3.0"):
        from .planning import validate_links
        errors.extend(validate_links(project, artifact_root))
        if version in ("1.2.0", "1.3.0"):
            from .grounding import validate_grounding
            errors.extend(validate_grounding(project, artifact_root))
        if version == "1.3.0":
            from .semantic_review import validate_review
            errors.extend(validate_review(project, artifact_root))
    return errors


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def new_project(project_id: str, name: str, description: str = "") -> dict:
    return {
        "schema_version": "1.0.0",
        "project": {
            "id": project_id,
            "name": name,
            "created_at": now_iso(),
            "description": description,
            "model_versions": {},
        },
        "sources": [],
        "segments": [],
        "events": [],
    }


def add_source(project: dict, source_id: str, path: str, duration_s: float, **kwargs: Any) -> dict:
    source = {
        "id": source_id,
        "path": str(path),
        "duration_s": float(duration_s),
        "sha256": kwargs.pop("sha256", None),
        "fps": kwargs.pop("fps", None),
        "width": kwargs.pop("width", None),
        "height": kwargs.pop("height", None),
        "captured_at": kwargs.pop("captured_at", None),
        "notes": kwargs.pop("notes", ""),
    }
    source.update(kwargs)
    project["sources"].append(source)
    return source


def add_event(project: dict, event: dict) -> dict:
    """追加事件并自动补 order / 缺省字段。"""
    event.setdefault("id", f"evt_{len(project['events']) + 1:06d}")
    event.setdefault("order", len(project["events"]))
    event.setdefault("game_time", None)
    event.setdefault("sim_time", None)
    event.setdefault("segment_id", None)
    event.setdefault("preconditions", [])
    event.setdefault("expected_result", {"text": "", "checks": []})
    event.setdefault("observed_result", {"text": "", "checks": []})
    event.setdefault("review", {"status": "pending"})
    event.setdefault("notes", "")
    project["events"].append(event)
    return event


def summarise(project: dict) -> dict:
    events = project.get("events", [])
    by_action: dict[str, int] = {}
    by_state: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    confidences = []
    known_positions = 0
    for event in events:
        action = (event.get("action") or {}).get("type", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
        state = event.get("state_status", "unknown")
        by_state[state] = by_state.get(state, 0) + 1
        layer = ((event.get("position") or {}).get("map") or {}).get("layer", "unknown")
        by_layer[layer] = by_layer.get(layer, 0) + 1
        confidences.append(float(event.get("confidence", 0)))
        if ((event.get("position") or {}).get("map") or {}).get("x") is not None:
            known_positions += 1
    return {
        "project_id": project.get("project", {}).get("id"),
        "sources": len(project.get("sources", [])),
        "segments": len(project.get("segments", [])),
        "events": len(events),
        "by_action": dict(sorted(by_action.items(), key=lambda kv: -kv[1])),
        "by_state": by_state,
        "by_layer": by_layer,
        "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "events_with_map_position": known_positions,
        "review_pending": sum(
            1 for e in events if (e.get("review") or {}).get("status") == "pending"
        ),
    }


def load_project(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_project(project: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
