from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.migrations import MigrationCompatibilityError, registry_snapshot
from web_cabinet.db import connect, init_db


LEGACY_JOBS_SQL = """
CREATE TABLE jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  user TEXT NOT NULL,
  command TEXT NOT NULL,
  args_json TEXT NOT NULL,
  log_path TEXT NOT NULL,
  result_json TEXT,
  exit_code INTEGER
);
"""

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

LEGACY_CONNECTOR_RUNS_SQL = """
CREATE TABLE connector_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  connector_run_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL,
  connector_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  schedule_slot TEXT,
  status TEXT NOT NULL CHECK(status IN ('running','success','failed','noop','stub')),
  created_at TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  data_version TEXT,
  message TEXT,
  config_path TEXT,
  outputs_json TEXT NOT NULL DEFAULT '{}',
  selected_files_json TEXT NOT NULL DEFAULT '[]',
  ingest_summaries_json TEXT NOT NULL DEFAULT '[]',
  error_text TEXT
);
"""


def test_t17_03_registry_snapshot_exposes_supported_components() -> None:
    snapshot = registry_snapshot()
    assert snapshot["schema"] == "genomeai.migration_registry.v1"
    versions = {item["component"]: item for item in snapshot["items"]}
    assert versions["web.db"]["current_version"] >= 1
    assert versions["backup_manifest"]["current_version"] >= versions["backup_manifest"]["supported_from"]
    assert versions["pilot_pack"]["supported_from"] == 1


def test_t17_03_init_db_upgrades_legacy_snapshot_and_records_registry(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_web.db"
    conn = connect(db_path)
    try:
        conn.executescript(LEGACY_JOBS_SQL)
        conn.executescript(LEGACY_AUDIT_LOG_SQL)
        conn.executescript(LEGACY_CONNECTOR_RUNS_SQL)
        conn.execute(
            "INSERT INTO jobs(kind, status, created_at, started_at, finished_at, user, command, args_json, log_path, result_json, exit_code) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "qc",
                "done",
                "2026-03-19T20:00:00+00:00",
                "2026-03-19T20:01:00+00:00",
                "2026-03-19T20:02:00+00:00",
                "operator",
                "python -m genomeai qc",
                json.dumps({"data_version": "dv_old", "run_id": "run_old"}),
                "logs/qc.log",
                json.dumps({"kv": {"qc_run": "qc_old"}}),
                0,
            ),
        )
        conn.execute(
            "INSERT INTO audit_log(ts, tenant_id, user_id, username, role, action, object_type, object_id, data_version, run_id, before_json, after_json, ip, user_agent, status, error, request_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "2026-03-19T20:00:00+00:00",
                "default",
                1,
                "operator",
                "operator",
                "pipeline.run.qc",
                "dataset",
                "dm_animals",
                "dv_old",
                "run_old",
                None,
                '{"ok": true}',
                None,
                None,
                "OK",
                None,
                "REQ-OLD",
            ),
        )
        conn.execute(
            "INSERT INTO connector_runs(connector_run_id, tenant_id, connector_id, kind, trigger_type, schedule_slot, status, created_at, started_at, finished_at, data_version, message, config_path, outputs_json, selected_files_json, ingest_summaries_json, error_text) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "cr_old",
                "default",
                "file_demo",
                "file",
                "manual",
                None,
                "success",
                "2026-03-19T20:00:00+00:00",
                "2026-03-19T20:00:00+00:00",
                "2026-03-19T20:00:01+00:00",
                "dv_old",
                "ok",
                "configs/connectors/file_demo.yaml",
                "{}",
                "[]",
                "[]",
                None,
            ),
        )
        conn.commit()

        init_db(conn)

        registry = {
            row[0]: {"version": int(row[1]), "details": json.loads(str(row[2]))}
            for row in conn.execute("SELECT component, version, details_json FROM schema_registry").fetchall()
        }
        assert registry["web.db"]["version"] >= 1
        assert registry["web.db.jobs"]["version"] == 2
        assert registry["web.db.audit_log"]["version"] == 2
        assert registry["web.db.connector_runs"]["version"] == 2
        assert registry["web.db.audit_log"]["details"]["append_only"] is True

        jobs_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert {"public_job_id", "queue_name", "pipeline_key", "artifacts_json", "error_text"}.issubset(jobs_columns)
        jobs_row = conn.execute("SELECT public_job_id, data_version, run_id FROM jobs ORDER BY id LIMIT 1").fetchone()
        assert jobs_row is not None
        assert jobs_row[0]
        assert jobs_row[1] == "dv_old"
        assert jobs_row[2] == "run_old"

        audit_row = conn.execute("SELECT schema_version, object_ref, action_group FROM audit_log ORDER BY id LIMIT 1").fetchone()
        assert audit_row is not None
        assert int(audit_row[0]) == 2
        assert audit_row[1] == "dataset:dm_animals"
        assert audit_row[2] == "run"

        connector_sql = str(conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='connector_runs'").fetchone()[0])
        assert "'partial'" in connector_sql
    finally:
        conn.close()


def test_t17_03_init_db_rejects_future_snapshot_registry(tmp_path: Path) -> None:
    db_path = tmp_path / "future_web.db"
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE schema_registry (component TEXT PRIMARY KEY, version INTEGER NOT NULL, updated_at TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}')"
        )
        conn.execute(
            "INSERT INTO schema_registry(component, version, updated_at, details_json) VALUES(?,?,?,?)",
            ("web.db", 999, "2026-03-20T00:00:00+00:00", "{}"),
        )
        conn.commit()

        with pytest.raises(MigrationCompatibilityError, match="newer than supported"):
            init_db(conn)
    finally:
        conn.close()
