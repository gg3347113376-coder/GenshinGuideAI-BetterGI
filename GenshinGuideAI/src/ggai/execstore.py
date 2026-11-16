"""执行结果存储：写入/读取 SQLite 的 exec_runs 表。"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .store import init_db


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def save_exec_run(
    db_path: str | Path,
    env: str,
    status: str,
    report: dict,
    sim_run_id: str | None = None,
) -> str:
    init_db(db_path)
    run_id = f"exec_{uuid.uuid4().hex[:12]}"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO exec_runs(id, sim_run_id, created_at, env, status, report)"
            " VALUES (?,?,?,?,?,?)",
            (
                run_id,
                sim_run_id,
                _now(),
                env,
                status,
                json.dumps(report, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def list_exec_runs(db_path: str | Path, limit: int = 50) -> list[dict]:
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM exec_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "sim_run_id": row["sim_run_id"],
                "created_at": row["created_at"],
                "env": row["env"],
                "status": row["status"],
                "report": json.loads(row["report"] or "{}"),
            }
            for row in rows
        ]
    finally:
        conn.close()
