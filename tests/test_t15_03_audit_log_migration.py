from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from web_cabinet.db import connect, init_db


LEGACY_AUDIT_LOG_SQL = """
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  username TEXT NOT NULL,
  role TEXT NOT NULL,
  action TEXT NOT NULL,
  object_type TEXT,
  object_id TEXT,
  data_version TEXT,
  run_id TEXT,
  before_json TEXT,
  after_json TEXT,
  ip TEXT,
  user_agent TEXT,
  status TEXT NOT NULL,
  error TEXT,
  request_id TEXT
);
"""


def test_t15_03_init_db_bootstraps_legacy_audit_log_schema_without_failing(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_web.db"
    conn = connect(db_path)
    try:
        conn.executescript(LEGACY_AUDIT_LOG_SQL)
        conn.execute(
            "INSERT INTO audit_log (ts, tenant_id, user_id, username, role, action, object_type, object_id, data_version, run_id, before_json, after_json, ip, user_agent, status, error, request_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-03-13T12:00:00+00:00",
                "default",
                1,
                "operator",
                "operator",
                "pipeline.run.qc",
                "animal",
                "A001",
                "dv_legacy",
                "run_legacy",
                None,
                '{"ok": true}',
                None,
                None,
                "OK",
                None,
                "req-1",
            ),
        )
        conn.commit()

        init_db(conn)

        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
        assert {"action_group", "object_ref", "schema_version", "archived_at", "archive_reason", "archive_batch_id"}.issubset(columns)

        trigger_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='audit_log'").fetchall()}
        assert {"trg_audit_log_no_update", "trg_audit_log_no_delete"}.issubset(trigger_names)

        row = conn.execute("SELECT schema_version, object_ref, action_group FROM audit_log ORDER BY id LIMIT 1").fetchone()
        assert row is not None
        assert int(row[0]) == 2
        assert row[1] == "animal:A001"
        assert row[2] == "run"
    finally:
        conn.close()


def test_t15_03_init_db_preserves_append_only_after_backfill(tmp_path: Path) -> None:
    db_path = tmp_path / "append_only_web.db"
    conn = connect(db_path)
    try:
        conn.executescript(LEGACY_AUDIT_LOG_SQL)
        conn.execute(
            "INSERT INTO audit_log (ts, tenant_id, user_id, username, role, action, object_type, object_id, data_version, run_id, before_json, after_json, ip, user_agent, status, error, request_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-03-13T12:00:00+00:00",
                "default",
                1,
                "operator",
                "operator",
                "upload.file",
                "dataset",
                "dm_farms",
                "dv_legacy",
                "run_legacy",
                None,
                '{"ok": true}',
                None,
                None,
                "OK",
                None,
                "req-2",
            ),
        )
        conn.commit()

        init_db(conn)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE audit_log SET status='FAIL' WHERE id=1")

        conn.execute(
            "UPDATE audit_log SET archived_at=?, archive_reason=?, archive_batch_id=? WHERE id=1",
            ("2026-03-13T12:30:00+00:00", "retention", "batch-1"),
        )
        row = conn.execute("SELECT archived_at, archive_reason, archive_batch_id FROM audit_log WHERE id=1").fetchone()
        assert row is not None
        assert row[0] == "2026-03-13T12:30:00+00:00"
        assert row[1] == "retention"
        assert row[2] == "batch-1"
    finally:
        conn.close()
