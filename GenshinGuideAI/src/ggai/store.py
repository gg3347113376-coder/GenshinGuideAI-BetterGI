"""SQLite 存储：项目导入/导出与统计。"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

DDL_PATH = Path(__file__).resolve().parents[2] / "schema" / "sqlite_v1.sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(DDL_PATH.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '1.0.0')"
        )
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('storage_version', '1.1.0')")
        conn.commit()
    finally:
        conn.close()


def _dumps(value) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def import_project(project: dict, db_path: str | Path) -> dict:
    init_db(db_path)
    conn = connect(db_path)
    try:
        meta = project["project"]
        conn.execute("BEGIN IMMEDIATE")
        source_ids = {item["id"] for item in project.get("sources", [])}
        segments = {item["id"]: item for item in project.get("segments", [])}
        for table in ("sources", "segments", "events"):
            items = project.get(table, [])
            if len({item["id"] for item in items}) != len(items):
                raise ValueError(f"{table}: duplicate id")
            for item in items:
                if table == "segments":
                    owner = conn.execute(
                        "SELECT s.project_id FROM segments g JOIN sources s ON s.id=g.source_id WHERE g.id=?",
                        (item["id"],),
                    ).fetchone()
                else:
                    owner = conn.execute(f"SELECT project_id FROM {table} WHERE id=?", (item["id"],)).fetchone()
                if owner and owner[0] != meta["id"]:
                    raise ValueError(f"{table}/{item['id']}: id belongs to another project; use unique ids")
        for item in [*project.get("segments", []), *project.get("events", [])]:
            if item["source_id"] not in source_ids:
                raise ValueError("source_id must belong to the imported project")
        for event in project.get("events", []):
            segment_id = event.get("segment_id")
            if segment_id and (segment_id not in segments or segments[segment_id]["source_id"] != event["source_id"]):
                raise ValueError("segment_id must belong to the event source")
        conn.execute(
            "INSERT INTO projects(id, name, created_at, description, schema_version)"
            " VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " created_at=excluded.created_at, description=excluded.description, schema_version=excluded.schema_version",
            (
                meta["id"],
                meta["name"],
                meta["created_at"],
                meta.get("description", ""),
                project["schema_version"],
            ),
        )
        conn.execute("DELETE FROM events WHERE project_id=?", (meta["id"],))
        conn.execute("DELETE FROM sources WHERE project_id=?", (meta["id"],))
        for source in project.get("sources", []):
            conn.execute(
                "INSERT OR REPLACE INTO sources(id, project_id, path, sha256, duration_s, fps,"
                " width, height, captured_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    source["id"],
                    meta["id"],
                    source["path"],
                    source.get("sha256"),
                    source["duration_s"],
                    source.get("fps"),
                    source.get("width"),
                    source.get("height"),
                    source.get("captured_at"),
                    source.get("notes", ""),
                ),
            )
        for segment in project.get("segments", []):
            conn.execute(
                "INSERT OR REPLACE INTO segments(id, source_id, start_s, end_s, kind, confidence, notes)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    segment["id"],
                    segment["source_id"],
                    segment["start_s"],
                    segment["end_s"],
                    segment["kind"],
                    segment.get("confidence"),
                    segment.get("notes", ""),
                ),
            )
        for event in project.get("events", []):
            vt = event["video_time"]
            gt = event.get("game_time") or {}
            actor = event.get("actor") or {}
            action = event["action"]
            pos = event.get("position") or {}
            mp = pos.get("map") or {}
            wp = pos.get("world") or {}
            conn.execute(
                "INSERT INTO events(id, project_id, source_id, segment_id, seq, video_start_s,"
                " video_end_s, video_precision, game_start_s, game_end_s, actor_kind, actor_name,"
                " action_type, action_params, action_method, map_x, map_y, map_layer, map_region,"
                " map_anchor, map_error_m, map_method, map_confidence, world_x, world_y, world_z,"
                " world_error_m, world_method, world_confidence, state_status, confidence, notes)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event["id"],
                    meta["id"],
                    event["source_id"],
                    event.get("segment_id"),
                    event["order"],
                    vt["start_s"],
                    vt["end_s"],
                    vt.get("precision", "unknown"),
                    gt.get("start_s"),
                    gt.get("end_s"),
                    actor.get("kind"),
                    actor.get("name", ""),
                    action["type"],
                    _dumps(action.get("params", {})),
                    action.get("method", "unknown"),
                    mp.get("x"),
                    mp.get("y"),
                    mp.get("layer"),
                    mp.get("region", ""),
                    mp.get("anchor", ""),
                    mp.get("error_m"),
                    mp.get("method", "unknown"),
                    mp.get("confidence"),
                    wp.get("x"),
                    wp.get("y"),
                    wp.get("z"),
                    wp.get("error_m"),
                    wp.get("method"),
                    wp.get("confidence"),
                    event["state_status"],
                    event["confidence"],
                    event.get("notes", ""),
                ),
            )
            for ev in event.get("evidence", []):
                conn.execute(
                    "INSERT INTO evidence(event_id, kind, t_s, path, bbox, text, note)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (
                        event["id"],
                        ev["kind"],
                        ev.get("t_s"),
                        ev.get("path", ""),
                        _dumps(ev.get("bbox")),
                        ev.get("text", ""),
                        ev.get("note", ""),
                    ),
                )
            review = event.get("review")
            if review:
                conn.execute(
                    "INSERT OR REPLACE INTO reviews(event_id, status, reviewed_by, reviewed_at, diff)"
                    " VALUES (?,?,?,?,?)",
                    (
                        event["id"],
                        review.get("status", "pending"),
                        review.get("by", ""),
                        review.get("at", ""),
                        _dumps(review.get("diff")),
                    ),
                )
        conn.execute(
            "INSERT INTO project_payloads(project_id, payload) VALUES (?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload",
            (meta["id"], json.dumps(project, ensure_ascii=False, allow_nan=False)),
        )
        conn.commit()
        return {
            "db": str(db_path),
            "project": meta["id"],
            "sources": len(project.get("sources", [])),
            "segments": len(project.get("segments", [])),
            "events": len(project.get("events", [])),
        }
    finally:
        conn.close()


def export_project(db_path: str | Path, project_id: str | None = None) -> dict:
    conn = connect(db_path)
    try:
        if project_id is None:
            rows = conn.execute("SELECT * FROM projects ORDER BY id LIMIT 2").fetchall()
            if len(rows) > 1:
                raise ValueError("数据库有多个项目，请指定 project_id")
            meta = rows[0] if rows else None
        else:
            meta = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if meta is None:
            raise ValueError("数据库中没有任何项目")
        payload_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_payloads'").fetchone()
        if payload_table:
            row = conn.execute("SELECT payload FROM project_payloads WHERE project_id=?", (meta["id"],)).fetchone()
            if row:
                return json.loads(row["payload"])
        warnings.warn("旧版数据库没有完整 JSON；已丢失字段无法恢复，请从原 JSON 重新导入。", UserWarning, stacklevel=2)
        project = {
            "schema_version": meta["schema_version"],
            "project": {
                "id": meta["id"],
                "name": meta["name"],
                "created_at": meta["created_at"],
                "description": meta["description"] or "",
                "model_versions": {},
            },
            "sources": [],
            "segments": [],
            "events": [],
        }
        for row in conn.execute("SELECT * FROM sources WHERE project_id=? ORDER BY id", (meta["id"],)):
            project["sources"].append(
                {
                    "id": row["id"],
                    "path": row["path"],
                    "sha256": row["sha256"],
                    "duration_s": row["duration_s"],
                    "fps": row["fps"],
                    "width": row["width"],
                    "height": row["height"],
                    "captured_at": row["captured_at"],
                    "notes": row["notes"] or "",
                }
            )
        for row in conn.execute("SELECT g.* FROM segments g JOIN sources s ON s.id=g.source_id WHERE s.project_id=? ORDER BY g.start_s", (meta["id"],)):
            project["segments"].append(
                {
                    "id": row["id"],
                    "source_id": row["source_id"],
                    "start_s": row["start_s"],
                    "end_s": row["end_s"],
                    "kind": row["kind"],
                    "confidence": row["confidence"],
                    "notes": row["notes"] or "",
                }
            )
        for row in conn.execute("SELECT * FROM events WHERE project_id=? ORDER BY seq", (meta["id"],)):
            event = {
                "id": row["id"],
                "source_id": row["source_id"],
                "segment_id": row["segment_id"],
                "order": row["seq"],
                "video_time": {
                    "start_s": row["video_start_s"],
                    "end_s": row["video_end_s"],
                    "precision": row["video_precision"] or "unknown",
                },
                "game_time": (
                    {"start_s": row["game_start_s"], "end_s": row["game_end_s"]}
                    if row["game_start_s"] is not None
                    else None
                ),
                "sim_time": None,
                "actor": {
                    "kind": row["actor_kind"] or "unknown",
                    "name": row["actor_name"] or "",
                },
                "action": {
                    "type": row["action_type"],
                    "params": json.loads(row["action_params"] or "{}"),
                    "method": row["action_method"] or "unknown",
                },
                "position": {
                    "map": {
                        "x": row["map_x"],
                        "y": row["map_y"],
                        "layer": row["map_layer"] or "unknown",
                        "region": row["map_region"] or "",
                        "anchor": row["map_anchor"] or "",
                        "error_m": row["map_error_m"],
                        "method": row["map_method"] or "unknown",
                        "confidence": row["map_confidence"] or 0,
                    },
                    "world": {
                        "x": row["world_x"],
                        "y": row["world_y"],
                        "z": row["world_z"],
                        "error_m": row["world_error_m"],
                        "method": row["world_method"] or "unknown",
                        "confidence": row["world_confidence"] or 0,
                    },
                },
                "preconditions": [],
                "expected_result": {"text": "", "checks": []},
                "observed_result": {"text": "", "checks": []},
                "state_status": row["state_status"],
                "confidence": row["confidence"],
                "evidence": [],
                "review": {"status": "pending"},
                "notes": row["notes"] or "",
            }
            for ev in conn.execute(
                "SELECT * FROM evidence WHERE event_id=? ORDER BY id", (row["id"],)
            ):
                event["evidence"].append(
                    {
                        "kind": ev["kind"],
                        "t_s": ev["t_s"],
                        "path": ev["path"] or "",
                        "bbox": json.loads(ev["bbox"]) if ev["bbox"] else None,
                        "text": ev["text"] or "",
                        "note": ev["note"] or "",
                    }
                )
            review = conn.execute(
                "SELECT * FROM reviews WHERE event_id=?", (row["id"],)
            ).fetchone()
            if review:
                event["review"] = {
                    "status": review["status"],
                    "by": review["reviewed_by"] or "",
                    "at": review["reviewed_at"] or "",
                    "diff": json.loads(review["diff"]) if review["diff"] else None,
                }
            project["events"].append(event)
        return project
    finally:
        conn.close()
