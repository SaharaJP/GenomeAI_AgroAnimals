from __future__ import annotations

"""Assistant query/answer logging (T8-02).

Логи пишутся в web_cabinet/storage/web.db (SQLite) *append-only*.
Таблица создаётся автоматически (без миграций), чтобы Streamlit мог работать
без запуска Flask web_cabinet.
"""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .ai_assistant_rag import AssistantResponse


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS assistant_log_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT NOT NULL,
          tenant_id TEXT NOT NULL,
          user_id INTEGER,
          username TEXT,
          question TEXT NOT NULL,
          status TEXT NOT NULL,
          refusal_reason TEXT,
          data_version TEXT,
          model_version TEXT,
          report_version TEXT,
          response_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assistant_log_v1_ts ON assistant_log_v1(ts);
        CREATE INDEX IF NOT EXISTS idx_assistant_log_v1_tenant ON assistant_log_v1(tenant_id);
        """
    )
    conn.commit()


def append_assistant_log(
    *,
    db_path: Path,
    ts: str,
    tenant_id: str,
    user_id: Optional[int],
    username: Optional[str],
    response: AssistantResponse,
) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn)
        g = response.guardrails or {}
        v = response.versions or {}
        status = "ok" if g.get("allowed") else "refused"
        refusal_reason = g.get("reason") if status == "refused" else None

        conn.execute(
            """
            INSERT INTO assistant_log_v1(
              ts, tenant_id, user_id, username, question,
              status, refusal_reason,
              data_version, model_version, report_version,
              response_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ts,
                str(tenant_id),
                int(user_id) if user_id is not None else None,
                str(username) if username is not None else None,
                str(response.question),
                status,
                refusal_reason,
                str(v.get("data_version", "NA")),
                str(v.get("model_version", "NA")),
                str(v.get("report_version", "NA")),
                json.dumps(asdict(response), ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
    finally:
        conn.close()


def list_assistant_logs(
    *,
    db_path: Path,
    tenant_id: str,
    limit: int = 200,
) -> list[Dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM assistant_log_v1 WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
            (str(tenant_id), int(limit)),
        ).fetchall()
        out: list[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["response"] = json.loads(d.get("response_json") or "{}")
            except Exception:
                d["response"] = {}
            out.append(d)
        return out
    finally:
        conn.close()
