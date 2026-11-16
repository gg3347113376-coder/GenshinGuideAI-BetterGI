"""仿真结果存储：写入/读取 SQLite 的 sim_runs 表。"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .store import init_db


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def save_sim_run(
    db_path: str | Path,
    project_id: str,
    params: dict,
    rules_ver: str,
    seed: int,
    status: str,
    result: dict,
) -> str:
    init_db(db_path)
    run_id = f"sim_{uuid.uuid4().hex[:12]}"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO sim_runs(id, project_id, created_at, params, rules_ver, seed, status, result)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                project_id,
                _now(),
                json.dumps(params, ensure_ascii=False),
                rules_ver,
                seed,
                status,
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def list_sim_runs(db_path: str | Path, project_id: str | None = None) -> list[dict]:
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM sim_runs WHERE project_id=? ORDER BY created_at", (project_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sim_runs ORDER BY created_at").fetchall()
        return [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "created_at": row["created_at"],
                "params": json.loads(row["params"] or "{}"),
                "rules_ver": row["rules_ver"],
                "seed": row["seed"],
                "status": row["status"],
                "result": json.loads(row["result"] or "{}"),
            }
            for row in rows
        ]
    finally:
        conn.close()
