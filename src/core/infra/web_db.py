from __future__ import annotations

import json
import os
import sqlite3
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from web_cabinet.jobs_v2 import ACTIVE_JOB_STATUSES, JOB_STATUSES, infer_job_refs, iso_after_seconds, load_job_runner_config, new_public_job_id
from core.security import (
    ALL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    ROLE_ADMIN,
    ROLE_DIRECTOR,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    ROLE_VET,
    ROLE_ZOOTECH,
    ROLE_CONSULTANT,
    ROLE_PARTNER,
)
from core.migrations import (
    MigrationCompatibilityError,
    sync_runtime_schema_registry,
    validate_schema_registry,
)
from core.infra.queue_runtime import (
    QueueEnvelope,
    resolve_queue_runtime_broker,
    resolve_queue_runtime_settings,
)
from core.infra.runtime_storage import (
    resolve_runtime_storage_settings,
    runtime_storage_diagnostics,
    validate_sqlite_compat_access,
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Settings:
    project_root: Path
    storage_dir: Path
    artifacts_root: Path
    db_path: Path
    uploads_dir: Path
    logs_dir: Path
    configs_dir: Path
    deploy_profile: str
    runtime_storage_backend: str
    runtime_storage_diagnostics: dict[str, Any]

    # --- NFR controls (T9-01) ---
    # Limit upload sizes to protect memory/disk.
    max_upload_bytes: int
    max_mapping_bytes: int
    # Safety bound for long-running subprocess jobs started from Web Cabinet.
    job_timeout_sec: int
    connector_recovery_queue_limit: int


def get_settings() -> Settings:
    project_root = Path(os.environ.get("GENOMEAI_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
    storage_dir = Path(os.environ.get("GENOMEAI_WEB_STORAGE", project_root / "web_cabinet" / "storage")).resolve()
    artifacts_root = Path(os.environ.get("GENOMEAI_ARTIFACTS_ROOT", project_root / "artifacts")).resolve()

    sqlite_probe_path = storage_dir / "web.db"
    runtime = resolve_runtime_storage_settings(project_root=project_root, storage_dir=storage_dir, sqlite_db_path=sqlite_probe_path)

    db_path = storage_dir / ("sqlite_compat_disabled.sqlite" if runtime.backend == "postgres" and runtime.adult_mode else "web.db")
    uploads_dir = storage_dir / "uploads"
    logs_dir = storage_dir / "logs"
    configs_dir = storage_dir / "config_overrides"

    runtime = resolve_runtime_storage_settings(project_root=project_root, storage_dir=storage_dir, sqlite_db_path=db_path)
    runtime_diag = runtime_storage_diagnostics(runtime)

    # NFR controls
    # Defaults are chosen for an on-prem LAN deployment with typical CSV exports.
    # - Upload: 200 MB per file (farms/animals/lactations/...)
    # - Mapping YAML: 5 MB
    # - Job timeout: 30 minutes (can be tuned per farm/infra)
    max_upload_mb = int(os.environ.get("GENOMEAI_WEB_MAX_UPLOAD_MB", "200"))
    max_mapping_mb = int(os.environ.get("GENOMEAI_WEB_MAX_MAPPING_MB", "5"))
    job_timeout_sec = int(os.environ.get("GENOMEAI_JOB_TIMEOUT_SEC", "1800"))
    connector_recovery_queue_limit = int(os.environ.get("GENOMEAI_CONNECTOR_RECOVERY_QUEUE_LIMIT", "5"))

    uploads_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_root.mkdir(parents=True, exist_ok=True)

    return Settings(
        project_root=project_root,
        storage_dir=storage_dir,
        artifacts_root=artifacts_root,
        db_path=db_path,
        uploads_dir=uploads_dir,
        logs_dir=logs_dir,
        configs_dir=configs_dir,
        deploy_profile=runtime.profile,
        runtime_storage_backend=runtime.backend,
        runtime_storage_diagnostics=runtime_diag.as_dict(),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        max_mapping_bytes=max_mapping_mb * 1024 * 1024,
        job_timeout_sec=job_timeout_sec,
        connector_recovery_queue_limit=max(1, connector_recovery_queue_limit),
    )




def _queue_envelope_from_job_row(row: dict[str, Any]) -> QueueEnvelope:
    return QueueEnvelope(
        job_id=int(row.get("id") or 0),
        public_job_id=str(row.get("public_job_id") or ""),
        queue_name=str(row.get("queue_name") or "default"),
        kind=str(row.get("kind") or row.get("pipeline_key") or "job"),
        tenant_id=str(row.get("tenant_id") or "default"),
        user_id=int(row.get("user_id")) if row.get("user_id") not in (None, "") else None,
        data_version=str(row.get("data_version") or "").strip() or None,
        run_id=str(row.get("run_id") or row.get("report_version") or row.get("scoring_run") or row.get("model_version") or row.get("qc_run") or "").strip() or None,
        attempt_no=int(row.get("attempt_no") or 0),
        max_attempts=max(1, int(row.get("max_attempts") or 1)),
        enqueued_at=str(row.get("created_at") or utcnow_iso()),
    )


def _maybe_enqueue_job_runtime(row: dict[str, Any]) -> None:
    try:
        broker = resolve_queue_runtime_broker()
        settings = resolve_queue_runtime_settings()
        if str(settings.backend or "sqlite") != "redis":
            return
        envelope = _queue_envelope_from_job_row(row)
        broker.enqueue(envelope, idempotency_key=f"job:{envelope.public_job_id}")
    except Exception:
        return


def connect(db_path: Path) -> sqlite3.Connection:
    settings = get_settings()
    validate_sqlite_compat_access(
        db_path=db_path,
        project_root=settings.project_root,
        storage_dir=settings.storage_dir,
    )
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _jobs_table_sql(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
    return str(row[0] or "") if row else ""


def _connector_runs_table_sql(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='connector_runs'").fetchone()
    return str(row[0] or "") if row else ""


_AUDIT_LOG_UPDATE_GUARD_SQL = """
CREATE TRIGGER trg_audit_log_no_update
BEFORE UPDATE ON audit_log
WHEN NOT (
  OLD.archived_at IS NULL AND NEW.archived_at IS NOT NULL
  AND OLD.ts IS NEW.ts
  AND OLD.tenant_id IS NEW.tenant_id
  AND OLD.user_id IS NEW.user_id
  AND OLD.username IS NEW.username
  AND OLD.role IS NEW.role
  AND OLD.action IS NEW.action
  AND OLD.action_group IS NEW.action_group
  AND OLD.object_type IS NEW.object_type
  AND OLD.object_id IS NEW.object_id
  AND OLD.object_ref IS NEW.object_ref
  AND OLD.data_version IS NEW.data_version
  AND OLD.run_id IS NEW.run_id
  AND OLD.before_json IS NEW.before_json
  AND OLD.after_json IS NEW.after_json
  AND OLD.ip IS NEW.ip
  AND OLD.user_agent IS NEW.user_agent
  AND OLD.status IS NEW.status
  AND OLD.error IS NEW.error
  AND OLD.request_id IS NEW.request_id
  AND OLD.schema_version IS NEW.schema_version
)
BEGIN
  SELECT RAISE(ABORT, 'audit_log is append-only; only archive mark is allowed');
END;
"""

_AUDIT_LOG_DELETE_GUARD_SQL = """
CREATE TRIGGER trg_audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
  SELECT RAISE(ABORT, 'audit_log is append-only');
END;
"""


def _bootstrap_legacy_audit_log_schema(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, 'audit_log'):
        return
    audit_columns: list[tuple[str, str]] = [
        ('ts', 'TEXT'),
        ('tenant_id', 'TEXT'),
        ('user_id', 'INTEGER'),
        ('username', 'TEXT'),
        ('role', 'TEXT'),
        ('action', 'TEXT'),
        ('action_group', 'TEXT'),
        ('object_type', 'TEXT'),
        ('object_id', 'TEXT'),
        ('object_ref', 'TEXT'),
        ('data_version', 'TEXT'),
        ('run_id', 'TEXT'),
        ('before_json', 'TEXT'),
        ('after_json', 'TEXT'),
        ('ip', 'TEXT'),
        ('user_agent', 'TEXT'),
        ('status', 'TEXT'),
        ('error', 'TEXT'),
        ('request_id', 'TEXT'),
        ('schema_version', 'INTEGER NOT NULL DEFAULT 2'),
        ('archived_at', 'TEXT'),
        ('archive_reason', 'TEXT'),
        ('archive_batch_id', 'TEXT'),
    ]
    for column, ddl in audit_columns:
        if not _has_column(conn, 'audit_log', column):
            conn.execute(f'ALTER TABLE audit_log ADD COLUMN {column} {ddl}')


def _drop_audit_log_guards(conn: sqlite3.Connection) -> None:
    conn.execute('DROP TRIGGER IF EXISTS trg_audit_log_no_update')
    conn.execute('DROP TRIGGER IF EXISTS trg_audit_log_no_delete')


def _ensure_audit_log_support_objects(conn: sqlite3.Connection) -> None:
    conn.execute('CREATE TABLE IF NOT EXISTS audit_archive_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL UNIQUE, tenant_id TEXT NOT NULL, created_at TEXT NOT NULL, cutoff_ts TEXT NOT NULL, rows_archived INTEGER NOT NULL, reason TEXT NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_ts ON audit_log(tenant_id, ts DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_action ON audit_log(tenant_id, action, ts DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_group ON audit_log(tenant_id, action_group, ts DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_run ON audit_log(tenant_id, run_id, ts DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_object ON audit_log(tenant_id, object_type, object_id, ts DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_archived ON audit_log(tenant_id, archived_at, ts DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_archive_runs_tenant_ts ON audit_archive_runs(tenant_id, created_at DESC)')
    _drop_audit_log_guards(conn)
    conn.execute(_AUDIT_LOG_UPDATE_GUARD_SQL)
    conn.execute(_AUDIT_LOG_DELETE_GUARD_SQL)


def _ensure_users_v2_collaboration_columns(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "users_v2"):
        return
    columns: list[tuple[str, str]] = [
        ('external_org', 'TEXT'),
        ('collaboration_mode', "TEXT NOT NULL DEFAULT 'internal'"),
        ('allowed_farm_ids_json', "TEXT NOT NULL DEFAULT '[]'"),
        ('allowed_site_ids_json', "TEXT NOT NULL DEFAULT '[]'"),
        ('collaboration_flags_json', "TEXT NOT NULL DEFAULT '{}'"),
    ]
    for column, ddl in columns:
        if not _has_column(conn, 'users_v2', column):
            conn.execute(f"ALTER TABLE users_v2 ADD COLUMN {column} {ddl}")


COLLAB_NOTES_SQL = """
CREATE TABLE IF NOT EXISTS collaboration_notes_v1 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by_user_id INTEGER NOT NULL,
  created_by_username TEXT NOT NULL,
  created_by_role TEXT NOT NULL,
  collaboration_mode TEXT NOT NULL,
  external_org TEXT,
  kind TEXT NOT NULL CHECK(kind IN ('comment','recommendation','approval_request')),
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  farm_id TEXT,
  site_id TEXT,
  body TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','accepted','rejected','resolved')) DEFAULT 'open',
  reviewed_at TEXT,
  reviewed_by_user_id INTEGER,
  reviewed_by_username TEXT,
  review_comment TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  linked_note_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_collab_notes_tenant_object ON collaboration_notes_v1(tenant_id, object_type, object_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collab_notes_tenant_scope ON collaboration_notes_v1(tenant_id, farm_id, site_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collab_notes_tenant_status ON collaboration_notes_v1(tenant_id, status, created_at DESC);

CREATE TRIGGER IF NOT EXISTS trg_collaboration_notes_v1_no_delete
BEFORE DELETE ON collaboration_notes_v1
BEGIN
  SELECT RAISE(ABORT, 'collaboration_notes_v1 is append-only; logical review only');
END;
"""


def _ensure_collaboration_notes_table(conn: sqlite3.Connection) -> None:
    conn.executescript(COLLAB_NOTES_SQL)


def _create_jobs_table_v2(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          public_job_id TEXT NOT NULL UNIQUE,
          queue_name TEXT NOT NULL,
          pipeline_key TEXT NOT NULL,
          kind TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN {JOB_STATUSES!r}),
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          cancel_requested_at TEXT,
          cancelled_at TEXT,
          attempt_no INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 1,
          retry_of_job_id INTEGER,
          next_attempt_at TEXT,
          retry_source TEXT,
          user TEXT NOT NULL,
          command TEXT NOT NULL,
          args_json TEXT NOT NULL,
          log_path TEXT NOT NULL,
          artifacts_json TEXT NOT NULL DEFAULT '[]',
          result_json TEXT,
          error_text TEXT,
          exit_code INTEGER,
          tenant_id TEXT,
          user_id INTEGER,
          data_version TEXT,
          run_id TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_data_version ON jobs(data_version)")


def _ensure_jobs_table_v2(conn: sqlite3.Connection) -> None:
    required_cols = {
        'public_job_id', 'queue_name', 'pipeline_key', 'cancel_requested_at', 'cancelled_at',
        'attempt_no', 'max_attempts', 'retry_of_job_id', 'next_attempt_at', 'retry_source',
        'artifacts_json', 'error_text', 'tenant_id', 'user_id', 'data_version', 'run_id', 'qc_run', 'model_version',
        'scoring_run', 'report_version'
    }
    if not _has_table(conn, 'jobs'):
        _create_jobs_table_v2(conn)
        return
    cols = {r[1] for r in conn.execute('PRAGMA table_info(jobs)').fetchall()}
    sql = _jobs_table_sql(conn)
    if required_cols.issubset(cols) and 'cancel_requested' in sql and 'cancelled' in sql:
        _create_jobs_table_v2(conn)
        return

    rows = [dict(r) for r in conn.execute('SELECT * FROM jobs').fetchall()]
    conn.execute('ALTER TABLE jobs RENAME TO jobs_legacy_v1')
    _create_jobs_table_v2(conn)
    cfg = load_job_runner_config(get_settings().project_root)
    for row in rows:
        args_json = str(row.get('args_json') or '{}')
        try:
            args = json.loads(args_json)
        except Exception:
            args = {}
        refs = infer_job_refs(kind=str(row.get('kind') or 'job'), args=args if isinstance(args, dict) else {})
        conn.execute(
            """
            INSERT INTO jobs(
              id, public_job_id, queue_name, pipeline_key, kind, status, created_at, started_at, finished_at,
              cancel_requested_at, cancelled_at, attempt_no, max_attempts, retry_of_job_id, next_attempt_at, retry_source, user, command,
              args_json, log_path, artifacts_json, result_json, error_text, exit_code, tenant_id, user_id,
              data_version, run_id, qc_run, model_version, scoring_run, report_version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get('id'),
                row.get('public_job_id') or new_public_job_id(),
                row.get('queue_name') or cfg.queue_name_default,
                row.get('pipeline_key') or refs.get('pipeline_key') or str(row.get('kind') or 'job'),
                row.get('kind') or 'job',
                row.get('status') or 'queued',
                row.get('created_at') or utcnow_iso(),
                row.get('started_at'),
                row.get('finished_at'),
                row.get('cancel_requested_at'),
                row.get('cancelled_at'),
                int(row.get('attempt_no') or 0),
                int(row.get('max_attempts') or cfg.max_attempts_default),
                row.get('retry_of_job_id'),
                row.get('next_attempt_at'),
                row.get('retry_source'),
                row.get('user') or 'unknown',
                row.get('command') or '',
                args_json,
                row.get('log_path') or '',
                row.get('artifacts_json') or '[]',
                row.get('result_json'),
                row.get('error_text'),
                row.get('exit_code'),
                row.get('tenant_id') or 'default',
                row.get('user_id'),
                row.get('data_version') or refs.get('data_version'),
                row.get('run_id') or refs.get('run_id'),
                row.get('qc_run') or refs.get('qc_run'),
                row.get('model_version') or refs.get('model_version'),
                row.get('scoring_run') or refs.get('scoring_run'),
                row.get('report_version') or refs.get('report_version'),
            ),
        )
    conn.execute('DROP TABLE jobs_legacy_v1')


def _ensure_target_dm_schema(conn: sqlite3.Connection) -> None:
    """Idempotent: create target DM tables needed for analytics endpoints (SQLite dev/test path)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dm_farms (
          tenant_id TEXT NOT NULL DEFAULT 'default',
          farm_id   TEXT NOT NULL,
          farm_name TEXT NOT NULL,
          country_code TEXT,
          timezone TEXT,
          currency TEXT DEFAULT 'EUR',
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (tenant_id, farm_id)
        );

        CREATE TABLE IF NOT EXISTS dm_animals (
          tenant_id TEXT NOT NULL DEFAULT 'default',
          animal_id TEXT NOT NULL,
          farm_id TEXT NOT NULL,
          site_id TEXT,
          current_pen_id TEXT,
          master_animal_id TEXT,
          external_id TEXT,
          sex TEXT,
          birth_date TEXT,
          breed TEXT,
          status TEXT,
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (tenant_id, animal_id)
        );

        CREATE TABLE IF NOT EXISTS dm_lactations (
          tenant_id TEXT NOT NULL DEFAULT 'default',
          lactation_id TEXT NOT NULL,
          animal_id TEXT NOT NULL,
          lactation_no INTEGER NOT NULL,
          calving_date TEXT NOT NULL,
          dryoff_date TEXT,
          milk_305d_kg REAL,
          calving_outcome TEXT,
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (tenant_id, lactation_id),
          UNIQUE (tenant_id, animal_id, lactation_no)
        );

        CREATE TABLE IF NOT EXISTS dm_milkings_daily (
          tenant_id TEXT NOT NULL DEFAULT 'default',
          record_id TEXT NOT NULL,
          animal_id TEXT NOT NULL,
          lactation_id TEXT,
          date TEXT NOT NULL,
          milk_kg REAL NOT NULL,
          milking_count INTEGER,
          fat_pct REAL,
          protein_pct REAL,
          scc_cells_ml INTEGER,
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (tenant_id, record_id)
        );

        CREATE TABLE IF NOT EXISTS dm_health_events (
          tenant_id TEXT NOT NULL DEFAULT 'default',
          event_id TEXT NOT NULL,
          animal_id TEXT NOT NULL,
          event_date TEXT NOT NULL,
          event_type TEXT NOT NULL,
          severity TEXT,
          notes TEXT,
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (tenant_id, event_id)
        );

        CREATE TABLE IF NOT EXISTS dm_repro_events (
          tenant_id TEXT NOT NULL DEFAULT 'default',
          repro_event_id TEXT NOT NULL,
          animal_id TEXT NOT NULL,
          event_date TEXT NOT NULL,
          event_type TEXT NOT NULL,
          bull_id TEXT,
          result TEXT,
          notes TEXT,
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (tenant_id, repro_event_id)
        );
        """
    )


def init_db(conn: sqlite3.Connection) -> None:
    try:
        validate_schema_registry(conn)
    except MigrationCompatibilityError:
        raise

    # Legacy MVP tables (keep for backward compatibility)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','operator','viewer')),
          created_at TEXT NOT NULL
        );

        """
    )

    _ensure_jobs_table_v2(conn)
    _bootstrap_legacy_audit_log_schema(conn)

    # Target RBAC tables
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS roles (
          role TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS permissions (
          permission TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS role_permissions (
          role TEXT NOT NULL,
          permission TEXT NOT NULL,
          PRIMARY KEY(role, permission),
          FOREIGN KEY(role) REFERENCES roles(role) ON DELETE CASCADE,
          FOREIGN KEY(permission) REFERENCES permissions(permission) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS users_v2 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          username TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          UNIQUE(tenant_id, username)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT NOT NULL,
          tenant_id TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          username TEXT NOT NULL,
          role TEXT NOT NULL,
          action TEXT NOT NULL,
          action_group TEXT,
          object_type TEXT,
          object_id TEXT,
          object_ref TEXT,
          data_version TEXT,
          run_id TEXT,
          before_json TEXT,
          after_json TEXT,
          ip TEXT,
          user_agent TEXT,
          status TEXT NOT NULL,
          error TEXT,
          request_id TEXT,
          schema_version INTEGER NOT NULL DEFAULT 2,
          archived_at TEXT,
          archive_reason TEXT,
          archive_batch_id TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_archive_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          cutoff_ts TEXT NOT NULL,
          rows_archived INTEGER NOT NULL,
          reason TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_ts ON audit_log(tenant_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_action ON audit_log(tenant_id, action, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_group ON audit_log(tenant_id, action_group, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_run ON audit_log(tenant_id, run_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_object ON audit_log(tenant_id, object_type, object_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_archived ON audit_log(tenant_id, archived_at, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_archive_runs_tenant_ts ON audit_archive_runs(tenant_id, created_at DESC);

        DROP TRIGGER IF EXISTS trg_audit_log_no_update;
        CREATE TRIGGER trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        WHEN NOT (
          OLD.archived_at IS NULL AND NEW.archived_at IS NOT NULL
          AND OLD.ts IS NEW.ts
          AND OLD.tenant_id IS NEW.tenant_id
          AND OLD.user_id IS NEW.user_id
          AND OLD.username IS NEW.username
          AND OLD.role IS NEW.role
          AND OLD.action IS NEW.action
          AND OLD.action_group IS NEW.action_group
          AND OLD.object_type IS NEW.object_type
          AND OLD.object_id IS NEW.object_id
          AND OLD.object_ref IS NEW.object_ref
          AND OLD.data_version IS NEW.data_version
          AND OLD.run_id IS NEW.run_id
          AND OLD.before_json IS NEW.before_json
          AND OLD.after_json IS NEW.after_json
          AND OLD.ip IS NEW.ip
          AND OLD.user_agent IS NEW.user_agent
          AND OLD.status IS NEW.status
          AND OLD.error IS NEW.error
          AND OLD.request_id IS NEW.request_id
          AND OLD.schema_version IS NEW.schema_version
        )
        BEGIN
          SELECT RAISE(ABORT, 'audit_log is append-only; only archive mark is allowed');
        END;

        DROP TRIGGER IF EXISTS trg_audit_log_no_delete;
        CREATE TRIGGER trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
          SELECT RAISE(ABORT, 'audit_log is append-only');
        END;

        -- Alert Center v2 (append-only fields + lifecycle)
        CREATE TABLE IF NOT EXISTS alerts_v2 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          alert_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          alert_type TEXT NOT NULL,
          title TEXT NOT NULL,
          source TEXT NOT NULL,
          cause TEXT NOT NULL,
          confidence REAL,

          object_type TEXT NOT NULL,
          object_id TEXT NOT NULL,

          status TEXT NOT NULL CHECK(status IN ('new','acknowledged','resolved')),
          deadline TEXT,
          owner_user_id INTEGER,

          attachments_json TEXT NOT NULL DEFAULT '[]',
          why_json TEXT NOT NULL DEFAULT '{}',
          what_to_do_json TEXT NOT NULL DEFAULT '[]',

          data_version TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT,

          acknowledged_at TEXT,
          acknowledged_by INTEGER,
          resolved_at TEXT,
          resolved_by INTEGER,
          resolved_reason TEXT,

          dedupe_key TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_v2_tenant_status ON alerts_v2(tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_alerts_v2_type ON alerts_v2(alert_type);
        CREATE INDEX IF NOT EXISTS idx_alerts_v2_object ON alerts_v2(object_type, object_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_v2_deadline ON alerts_v2(deadline);
        CREATE INDEX IF NOT EXISTS idx_alerts_v2_dedupe ON alerts_v2(tenant_id, dedupe_key);

        -- Decision Log v2 (append-only)
        CREATE TABLE IF NOT EXISTS decision_log_v2 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          decision_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,

          recommendation_id TEXT,
          action TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          username TEXT NOT NULL,
          reason TEXT,
          comment TEXT,

          related_alert TEXT,

          object_type TEXT,
          object_id TEXT,
          farm_id TEXT,
          group_id TEXT,

          data_version TEXT,
          model_version TEXT,
          report_version TEXT,
          qc_run TEXT,
          scoring_run TEXT,

          metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_decision_v2_tenant_created ON decision_log_v2(tenant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_decision_v2_object ON decision_log_v2(object_type, object_id);
        CREATE INDEX IF NOT EXISTS idx_decision_v2_farm ON decision_log_v2(farm_id);
        CREATE INDEX IF NOT EXISTS idx_decision_v2_group ON decision_log_v2(group_id);
        CREATE INDEX IF NOT EXISTS idx_decision_v2_alert ON decision_log_v2(related_alert);
        CREATE INDEX IF NOT EXISTS idx_decision_v2_rec ON decision_log_v2(recommendation_id);

        -- T20-01 Unified operational animal events (append-only)
        CREATE TABLE IF NOT EXISTS animal_events_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          animal_id TEXT NOT NULL,
          farm_id TEXT,
          site_id TEXT,
          lactation_id TEXT,

          event_type TEXT NOT NULL,
          event_ts TEXT NOT NULL,
          event_date TEXT NOT NULL,

          actor_type TEXT NOT NULL,
          actor_user_id INTEGER,
          actor_username TEXT,

          source TEXT NOT NULL,
          source_ref TEXT,
          reason_code TEXT,

          linked_object_type TEXT,
          linked_object_id TEXT,
          linked_decision_id TEXT,
          linked_task_id TEXT,

          request_id TEXT,
          job_id TEXT,

          data_version TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT,

          payload_json TEXT NOT NULL DEFAULT '{}',
          schema_version INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_tenant_animal_ts ON animal_events_v1(tenant_id, animal_id, event_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_tenant_type_ts ON animal_events_v1(tenant_id, event_type, event_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_tenant_event_date ON animal_events_v1(tenant_id, event_date DESC);
        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_linked_object ON animal_events_v1(tenant_id, linked_object_type, linked_object_id, event_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_linked_task ON animal_events_v1(tenant_id, linked_task_id, event_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_linked_decision ON animal_events_v1(tenant_id, linked_decision_id, event_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_animal_events_v1_request ON animal_events_v1(tenant_id, request_id, event_ts DESC);

        -- T25-05 Mobile sync / conflict / retry journal for unstable connectivity scenarios
        CREATE TABLE IF NOT EXISTS mobile_sync_actions_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action_key TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          username TEXT NOT NULL,
          role TEXT NOT NULL,
          page_key TEXT,
          action_kind TEXT NOT NULL,
          object_type TEXT,
          object_id TEXT,
          status TEXT NOT NULL CHECK(status IN ('saved','pending_retry','conflict')),
          payload_hash TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          result_json TEXT,
          conflict_json TEXT,
          last_error TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0,
          request_id TEXT,
          linked_event_id TEXT,
          linked_worklist_id TEXT,
          linked_decision_id TEXT,
          data_version TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_mobile_sync_actions_tenant_user_updated ON mobile_sync_actions_v1(tenant_id, user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mobile_sync_actions_tenant_page_updated ON mobile_sync_actions_v1(tenant_id, page_key, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mobile_sync_actions_tenant_status_updated ON mobile_sync_actions_v1(tenant_id, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mobile_sync_actions_tenant_object ON mobile_sync_actions_v1(tenant_id, object_type, object_id, updated_at DESC);

        CREATE TRIGGER IF NOT EXISTS trg_animal_events_v1_no_update
        BEFORE UPDATE ON animal_events_v1
        BEGIN
          SELECT RAISE(ABORT, 'animal_events_v1 is append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_animal_events_v1_no_delete
        BEFORE DELETE ON animal_events_v1
        BEGIN
          SELECT RAISE(ABORT, 'animal_events_v1 is append-only');
        END;

        -- T14-05 Feedback loop (accept/reject recommendations + metrics/export)
        CREATE TABLE IF NOT EXISTS feedback_events_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          feedback_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,

          recommendation_id TEXT NOT NULL,
          decision TEXT NOT NULL CHECK(decision IN ('accepted','rejected')),
          reason_code TEXT NOT NULL,
          comment TEXT,

          recommendation_created_at TEXT,
          decision_seconds INTEGER,

          related_alert TEXT,
          task_id TEXT,

          object_type TEXT,
          object_id TEXT,
          farm_id TEXT,
          group_id TEXT,

          data_version TEXT,
          model_version TEXT,
          report_version TEXT,
          qc_run TEXT,
          scoring_run TEXT,

          feedback_source TEXT,
          decision_id TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_v1_tenant_created ON feedback_events_v1(tenant_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_v1_rec ON feedback_events_v1(tenant_id, recommendation_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_v1_object ON feedback_events_v1(tenant_id, object_type, object_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_v1_data_version ON feedback_events_v1(tenant_id, data_version, created_at DESC);

        CREATE TRIGGER IF NOT EXISTS trg_feedback_v1_no_update
        BEFORE UPDATE ON feedback_events_v1
        BEGIN
          SELECT RAISE(ABORT, 'feedback_events_v1 is append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_feedback_v1_no_delete
        BEFORE DELETE ON feedback_events_v1
        BEGIN
          SELECT RAISE(ABORT, 'feedback_events_v1 is append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_decision_v2_no_update
        BEFORE UPDATE ON decision_log_v2
        BEGIN
          SELECT RAISE(ABORT, 'decision_log_v2 is append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_decision_v2_no_delete
        BEFORE DELETE ON decision_log_v2
        BEGIN
          SELECT RAISE(ABORT, 'decision_log_v2 is append-only');
        END;

        -- Worklists / Tasks v1 (simple action lists derived from alerts/rules)
        CREATE TABLE IF NOT EXISTS tasks_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          task_type TEXT NOT NULL,
          title TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 3,

          status TEXT NOT NULL CHECK(status IN ('open','in_progress','done','cancelled')),
          due_at TEXT,
          owner_user_id INTEGER,

          related_alert TEXT,
          object_type TEXT,
          object_id TEXT,

          worklist_type TEXT,
          confidence REAL,
          linked_decision_id TEXT,
          linked_task_id TEXT,
          linked_source_facts_json TEXT NOT NULL DEFAULT '[]',

          attachments_json TEXT NOT NULL DEFAULT '[]',
          why_json TEXT NOT NULL DEFAULT '{}',
          what_to_do_json TEXT NOT NULL DEFAULT '[]',

          data_version TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT,

          started_at TEXT,
          closed_at TEXT,
          closed_by INTEGER,
          closed_reason TEXT,
          closed_comment TEXT,

          dedupe_key TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_v1_tenant_status ON tasks_v1(tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_v1_due ON tasks_v1(due_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_v1_owner ON tasks_v1(owner_user_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_v1_type ON tasks_v1(task_type);
        CREATE INDEX IF NOT EXISTS idx_tasks_v1_alert ON tasks_v1(related_alert);
        CREATE INDEX IF NOT EXISTS idx_tasks_v1_object ON tasks_v1(object_type, object_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_v1_dedupe ON tasks_v1(tenant_id, dedupe_key);

        CREATE TRIGGER IF NOT EXISTS trg_tasks_v1_no_delete
        BEFORE DELETE ON tasks_v1
        BEGIN
          SELECT RAISE(ABORT, 'tasks_v1 rows must not be deleted');
        END;

        CREATE TABLE IF NOT EXISTS completion_outcomes_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          outcome_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,

          worklist_id TEXT,
          task_id TEXT,
          linked_decision_id TEXT,
          related_alert TEXT,

          object_type TEXT,
          object_id TEXT,

          owner_user_id INTEGER,
          assignee_team TEXT,
          worklist_type TEXT,
          priority INTEGER,
          confidence REAL,
          due_at TEXT,

          outcome_status TEXT NOT NULL CHECK(outcome_status IN ('done','cancelled','deferred','no_effect','escalated')),
          reason_code TEXT NOT NULL,
          comment TEXT,

          outcome_by INTEGER,
          outcome_by_username TEXT,
          outcome_role TEXT,

          request_id TEXT,
          data_version TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT,

          metrics_json TEXT NOT NULL DEFAULT '{}',
          auto_actions_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_task ON completion_outcomes_v1(tenant_id, task_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_worklist ON completion_outcomes_v1(tenant_id, worklist_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_status ON completion_outcomes_v1(tenant_id, outcome_status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_alert ON completion_outcomes_v1(tenant_id, related_alert, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_decision ON completion_outcomes_v1(tenant_id, linked_decision_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_object ON completion_outcomes_v1(tenant_id, object_type, object_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_outcomes_v1_team ON completion_outcomes_v1(tenant_id, assignee_team, created_at DESC);

        CREATE TRIGGER IF NOT EXISTS trg_completion_outcomes_v1_no_update
        BEFORE UPDATE ON completion_outcomes_v1
        BEGIN
          SELECT RAISE(ABORT, 'completion_outcomes_v1 is append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_completion_outcomes_v1_no_delete
        BEFORE DELETE ON completion_outcomes_v1
        BEGIN
          SELECT RAISE(ABORT, 'completion_outcomes_v1 is append-only');
        END;



        CREATE TABLE IF NOT EXISTS treatment_journal_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          course_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          course_status TEXT NOT NULL CHECK(course_status IN ('planned','active','completed','cancelled')),
          animal_id TEXT NOT NULL,
          farm_id TEXT,
          site_id TEXT,
          pen_id TEXT,

          linked_alert_id TEXT,
          linked_health_event_id TEXT,
          linked_protocol_execution_id TEXT,
          linked_worklist_id TEXT,

          treatment_type TEXT NOT NULL,
          diagnosis_label TEXT,
          drug_name TEXT,
          drug_code TEXT,
          route TEXT,
          dose_value REAL,
          dose_unit TEXT,
          frequency_per_day INTEGER,
          duration_days INTEGER,

          start_date TEXT NOT NULL,
          end_date TEXT,
          follow_up_due_at TEXT,
          follow_up_status TEXT NOT NULL DEFAULT 'none' CHECK(follow_up_status IN ('none','due','done','cancelled')),
          follow_up_comment TEXT,

          withdrawal_rule_version TEXT,
          withdrawal_days_rule INTEGER,
          withdrawal_end_date_source TEXT,
          withdrawal_end_date_calc TEXT,
          withdrawal_end_date_effective TEXT,

          created_by INTEGER,
          created_by_username TEXT,
          created_by_role TEXT,
          completed_at TEXT,
          completed_by INTEGER,
          completed_by_username TEXT,

          request_id TEXT,
          data_version TEXT,
          source_versions_json TEXT NOT NULL DEFAULT '{}',
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_tenant_status ON treatment_journal_v1(tenant_id, course_status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_animal ON treatment_journal_v1(tenant_id, animal_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_withdrawal ON treatment_journal_v1(tenant_id, withdrawal_end_date_effective, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_followup ON treatment_journal_v1(tenant_id, follow_up_due_at, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_worklist ON treatment_journal_v1(tenant_id, linked_worklist_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_alert ON treatment_journal_v1(tenant_id, linked_alert_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_treatment_journal_v1_protocol ON treatment_journal_v1(tenant_id, linked_protocol_execution_id, updated_at DESC);
        CREATE TRIGGER IF NOT EXISTS trg_treatment_journal_v1_no_delete
        BEFORE DELETE ON treatment_journal_v1
        BEGIN
          SELECT RAISE(ABORT, 'treatment_journal_v1 rows must not be deleted');
        END;



CREATE TABLE IF NOT EXISTS drug_use_compliance_v1 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  event_at TEXT NOT NULL,

  course_id TEXT NOT NULL,
  animal_id TEXT NOT NULL,
  farm_id TEXT,
  site_id TEXT,
  pen_id TEXT,

  linked_object_type TEXT,
  linked_object_id TEXT,
  linked_alert_id TEXT,
  linked_health_event_id TEXT,
  linked_protocol_execution_id TEXT,
  linked_worklist_id TEXT,

  protocol_reference TEXT,

  drug_name TEXT,
  drug_code TEXT,
  route TEXT,
  dose_value REAL,
  dose_unit TEXT,

  action_type TEXT NOT NULL CHECK(action_type IN ('prescribed','approved','executed','rejected')),
  action_reason_code TEXT,
  action_comment TEXT,
  administration_date TEXT,

  approval_required INTEGER NOT NULL DEFAULT 0,
  approval_state TEXT NOT NULL DEFAULT 'not_required' CHECK(approval_state IN ('not_required','pending','approved','rejected')),

  prescribed_by INTEGER,
  prescribed_by_username TEXT,
  prescribed_by_role TEXT,
  prescribed_at TEXT,

  approved_by INTEGER,
  approved_by_username TEXT,
  approved_by_role TEXT,
  approved_at TEXT,
  approval_comment TEXT,

  executed_by INTEGER,
  executed_by_username TEXT,
  executed_by_role TEXT,
  executed_at TEXT,

  request_id TEXT,
  data_version TEXT,
  source_versions_json TEXT NOT NULL DEFAULT '{}',
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_drug_use_compliance_tenant_course ON drug_use_compliance_v1(tenant_id, course_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_drug_use_compliance_tenant_animal ON drug_use_compliance_v1(tenant_id, animal_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_drug_use_compliance_tenant_approval ON drug_use_compliance_v1(tenant_id, approval_state, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_drug_use_compliance_tenant_action ON drug_use_compliance_v1(tenant_id, action_type, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_drug_use_compliance_tenant_object ON drug_use_compliance_v1(tenant_id, linked_object_type, linked_object_id, event_at DESC);
CREATE TRIGGER IF NOT EXISTS trg_drug_use_compliance_no_update
BEFORE UPDATE ON drug_use_compliance_v1
BEGIN
  SELECT RAISE(ABORT, 'drug_use_compliance_v1 is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_drug_use_compliance_no_delete
BEFORE DELETE ON drug_use_compliance_v1
BEGIN
  SELECT RAISE(ABORT, 'drug_use_compliance_v1 is append-only');
END;

        CREATE TABLE IF NOT EXISTS vet_protocol_executions_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          execution_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          protocol_key TEXT NOT NULL,
          protocol_version INTEGER NOT NULL,
          protocol_title TEXT NOT NULL,
          catalog_version TEXT,
          status TEXT NOT NULL CHECK(status IN ('open','in_progress','completed','cancelled')),

          animal_id TEXT,
          farm_id TEXT,
          site_id TEXT,

          linked_alert_id TEXT,
          linked_health_event_id TEXT,
          linked_worklist_id TEXT,

          object_type TEXT,
          object_id TEXT,

          owner_user_id INTEGER,
          assignee_team TEXT,
          owner_role TEXT,

          started_by INTEGER,
          started_by_username TEXT,
          started_role TEXT,

          next_follow_up_due_at TEXT,
          completed_at TEXT,
          completed_by INTEGER,
          completed_by_username TEXT,

          request_id TEXT,
          data_version TEXT,
          qc_run TEXT,
          model_version TEXT,
          scoring_run TEXT,
          report_version TEXT,

          steps_json TEXT NOT NULL DEFAULT '[]',
          linked_treatments_json TEXT NOT NULL DEFAULT '[]',
          linked_observations_json TEXT NOT NULL DEFAULT '[]',
          source_versions_json TEXT NOT NULL DEFAULT '{}',
          metrics_json TEXT NOT NULL DEFAULT '{}',
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_vet_protocol_exec_tenant_status ON vet_protocol_executions_v1(tenant_id, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vet_protocol_exec_animal ON vet_protocol_executions_v1(tenant_id, animal_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vet_protocol_exec_worklist ON vet_protocol_executions_v1(tenant_id, linked_worklist_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vet_protocol_exec_alert ON vet_protocol_executions_v1(tenant_id, linked_alert_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vet_protocol_exec_protocol ON vet_protocol_executions_v1(tenant_id, protocol_key, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vet_protocol_exec_team ON vet_protocol_executions_v1(tenant_id, assignee_team, updated_at DESC);
        CREATE TRIGGER IF NOT EXISTS trg_vet_protocol_exec_no_delete
        BEFORE DELETE ON vet_protocol_executions_v1
        BEGIN
          SELECT RAISE(ABORT, 'vet_protocol_executions_v1 rows must not be deleted');
        END;

        -- NOTE: Workflow 2.0 extends tasks_v1 online via ALTER TABLE (see below).

        -- T10-04 Saved Views (user/shared)
        CREATE TABLE IF NOT EXISTS saved_views_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          view_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          created_by INTEGER NOT NULL,
          created_by_username TEXT NOT NULL,

          scope TEXT NOT NULL CHECK(scope IN ('user','shared')),
          name TEXT NOT NULL,
          description TEXT,
          page_key TEXT NOT NULL,
          state_json TEXT NOT NULL,

          data_version TEXT,
          run_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_saved_views_v1_tenant_page ON saved_views_v1(tenant_id, page_key);
        CREATE INDEX IF NOT EXISTS idx_saved_views_v1_tenant_creator ON saved_views_v1(tenant_id, created_by);

        -- T10-04 Report Templates (user/shared)
        CREATE TABLE IF NOT EXISTS report_templates_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          template_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          created_by INTEGER NOT NULL,
          created_by_username TEXT NOT NULL,

          scope TEXT NOT NULL CHECK(scope IN ('user','shared')),
          name TEXT NOT NULL,
          description TEXT,
          sections_json TEXT NOT NULL DEFAULT '[]',
          metrics_json TEXT NOT NULL DEFAULT '[]',
          options_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_templates_v1_tenant_creator ON report_templates_v1(tenant_id, created_by);

        -- T10-04 Favorites (reports, alerts, groups, animals)
        CREATE TABLE IF NOT EXISTS favorites_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          object_type TEXT NOT NULL,
          object_id TEXT NOT NULL,
          label TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(tenant_id, user_id, object_type, object_id)
        );
        CREATE INDEX IF NOT EXISTS idx_favorites_v1_tenant_user ON favorites_v1(tenant_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_favorites_v1_object ON favorites_v1(object_type, object_id);

        -- T11-02 Refdata: price books + assumptions (versioned)
        CREATE TABLE IF NOT EXISTS refdata_active (
          tenant_id TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('price_book','assumptions')),
          active_version_id TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(tenant_id, kind)
        );

        CREATE TABLE IF NOT EXISTS price_book_versions (
          version_id TEXT PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          effective_date TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_by INTEGER,
          comment TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_price_book_versions_tenant_eff ON price_book_versions(tenant_id, effective_date);

        CREATE TABLE IF NOT EXISTS price_book_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version_id TEXT NOT NULL,
          tenant_id TEXT NOT NULL,

          item_type TEXT NOT NULL,
          item_code TEXT NOT NULL,
          name TEXT,
          unit TEXT,
          currency TEXT,
          value REAL,

          farm_id TEXT,
          meta_json TEXT NOT NULL DEFAULT '{}',

          FOREIGN KEY(version_id) REFERENCES price_book_versions(version_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_price_book_items_ver ON price_book_items(version_id);
        CREATE INDEX IF NOT EXISTS idx_price_book_items_type_code ON price_book_items(tenant_id, item_type, item_code);

        CREATE TABLE IF NOT EXISTS assumptions_versions (
          version_id TEXT PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          effective_date TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_by INTEGER,
          comment TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_assumptions_versions_tenant_eff ON assumptions_versions(tenant_id, effective_date);

        CREATE TABLE IF NOT EXISTS assumptions_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version_id TEXT NOT NULL,
          tenant_id TEXT NOT NULL,

          key TEXT NOT NULL,
          value TEXT,
          unit TEXT,
          data_type TEXT NOT NULL DEFAULT 'str' CHECK(data_type IN ('str','int','float','bool','json')),
          meta_json TEXT NOT NULL DEFAULT '{}',

          FOREIGN KEY(version_id) REFERENCES assumptions_versions(version_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_assumptions_items_ver ON assumptions_items(version_id);
        CREATE INDEX IF NOT EXISTS idx_assumptions_items_key ON assumptions_items(tenant_id, key);

        -- T11-04 What-If scenarios (saved + approval)
        CREATE TABLE IF NOT EXISTS whatif_scenarios_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          scenario_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          name TEXT NOT NULL,
          description TEXT,
          status TEXT NOT NULL CHECK(status IN ('draft','approved','archived')),

          created_by INTEGER NOT NULL,
          created_by_username TEXT NOT NULL,

          approval_requested_at TEXT,
          approval_requested_by INTEGER,
          approval_requested_by_username TEXT,
          approval_request_comment TEXT,

          approved_at TEXT,
          approved_by INTEGER,
          approved_by_username TEXT,
          approval_comment TEXT,

          pdf_exported_at TEXT,
          pdf_exported_by INTEGER,
          pdf_exported_by_username TEXT,
          pdf_rel_path TEXT,

          rejected_at TEXT,
          rejected_by INTEGER,
          rejected_by_username TEXT,
          rejection_comment TEXT,

          cloned_from_scenario_id TEXT,

          archived_at TEXT,
          archived_by INTEGER,
          archived_by_username TEXT,
          archive_comment TEXT,

          data_version TEXT,
          params_json TEXT NOT NULL DEFAULT '{}',
          last_economics_run TEXT,
          last_run_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_whatif_scenarios_tenant_status ON whatif_scenarios_v1(tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_whatif_scenarios_tenant_created ON whatif_scenarios_v1(tenant_id, created_at);

        -- T11-04 What-If PDF reports (fact-based, no LLM)
        CREATE TABLE IF NOT EXISTS whatif_reports_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_by INTEGER NOT NULL,
          created_by_username TEXT NOT NULL,

          scenario_id TEXT NOT NULL,
          report_version TEXT NOT NULL,
          data_version TEXT NOT NULL,

          base_economics_run TEXT NOT NULL,
          scenario_economics_run TEXT NOT NULL,

          pdf_rel_path TEXT NOT NULL,
          params_json TEXT NOT NULL DEFAULT '{}',

          UNIQUE(tenant_id, report_version)
        );
        CREATE INDEX IF NOT EXISTS idx_whatif_reports_tenant_scenario ON whatif_reports_v1(tenant_id, scenario_id);
        CREATE INDEX IF NOT EXISTS idx_whatif_reports_tenant_created ON whatif_reports_v1(tenant_id, created_at);

        -- T12-03 Playbooks (versioned checklists for alerts/tasks)
        CREATE TABLE IF NOT EXISTS playbook_versions (
          version_id TEXT PRIMARY KEY,
          tenant_id TEXT NOT NULL,

          playbook_key TEXT NOT NULL,
          target_kind TEXT NOT NULL CHECK(target_kind IN ('alert','task')),
          target_type TEXT NOT NULL,
          farm_id TEXT NOT NULL DEFAULT '',

          name TEXT NOT NULL,
          description TEXT,
          steps_json TEXT NOT NULL DEFAULT '[]',

          created_at TEXT NOT NULL,
          created_by INTEGER,
          created_by_username TEXT,
          comment TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_playbook_versions_key ON playbook_versions(tenant_id, playbook_key, farm_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_playbook_versions_target ON playbook_versions(tenant_id, target_kind, target_type, farm_id);

        CREATE TABLE IF NOT EXISTS playbooks_active (
          tenant_id TEXT NOT NULL,
          playbook_key TEXT NOT NULL,
          farm_id TEXT NOT NULL DEFAULT '',
          active_version_id TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(tenant_id, playbook_key, farm_id)
        );

        -- T12-04 Weekly Plans (draft -> approved -> archived) + auto-tasks on approval
        CREATE TABLE IF NOT EXISTS weekly_plans_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          plan_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          week_start TEXT NOT NULL,
          name TEXT NOT NULL,
          summary TEXT,
          status TEXT NOT NULL CHECK(status IN ('draft','approved','archived')),

          farm_id TEXT,
          data_version TEXT,

          action_items_json TEXT NOT NULL DEFAULT '[]',

          created_by INTEGER NOT NULL,
          created_by_username TEXT NOT NULL,

          approved_at TEXT,
          approved_by INTEGER,
          approved_by_username TEXT,
          approval_comment TEXT,

          rejected_at TEXT,
          rejected_by INTEGER,
          rejected_by_username TEXT,
          rejection_comment TEXT,

          archived_at TEXT,
          archived_by INTEGER,
          archived_by_username TEXT,
          archive_comment TEXT,

          tasks_created_at TEXT,
          tasks_created_run_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_weekly_plans_tenant_status ON weekly_plans_v1(tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_weekly_plans_tenant_week ON weekly_plans_v1(tenant_id, week_start);
        CREATE INDEX IF NOT EXISTS idx_weekly_plans_tenant_created ON weekly_plans_v1(tenant_id, created_at);

        CREATE TABLE IF NOT EXISTS weekly_plan_tasks_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          plan_id TEXT NOT NULL,
          action_key TEXT NOT NULL,
          task_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(tenant_id, plan_id, action_key)
        );
        CREATE INDEX IF NOT EXISTS idx_weekly_plan_tasks_plan ON weekly_plan_tasks_v1(tenant_id, plan_id);

        -- T12-04 Approvals for regular Reports (artifacts/<dv>/reports/<report_version>/...)
        CREATE TABLE IF NOT EXISTS report_approvals_v1 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          data_version TEXT NOT NULL,
          report_version TEXT NOT NULL,

          status TEXT NOT NULL CHECK(status IN ('draft','approved','archived')),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,

          approved_at TEXT,
          approved_by INTEGER,
          approved_by_username TEXT,
          approval_comment TEXT,

          rejected_at TEXT,
          rejected_by INTEGER,
          rejected_by_username TEXT,
          rejection_comment TEXT,

          archived_at TEXT,
          archived_by INTEGER,
          archived_by_username TEXT,
          archive_comment TEXT,

          UNIQUE(tenant_id, data_version, report_version)
        );
        CREATE INDEX IF NOT EXISTS idx_report_approvals_dv ON report_approvals_v1(tenant_id, data_version);
        CREATE INDEX IF NOT EXISTS idx_report_approvals_status ON report_approvals_v1(tenant_id, status);
        """
    )

    # Online schema upgrade: rejection fields (T12-04 approvals)
    if _has_column(conn, 'whatif_scenarios_v1', 'scenario_id'):
        if not _has_column(conn, 'whatif_scenarios_v1', 'rejected_at'):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN rejected_at TEXT")
        if not _has_column(conn, 'whatif_scenarios_v1', 'rejected_by'):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN rejected_by INTEGER")
        if not _has_column(conn, 'whatif_scenarios_v1', 'rejected_by_username'):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN rejected_by_username TEXT")
        if not _has_column(conn, 'whatif_scenarios_v1', 'rejection_comment'):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN rejection_comment TEXT")

    # Online schema upgrade for T12-01 Workflow 2.0 (additive-only)
    # Extend tasks_v1 with domain/SLA/team assignment fields.
    if _has_column(conn, "tasks_v1", "task_id"):
        if not _has_column(conn, "tasks_v1", "domain"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN domain TEXT")
        if not _has_column(conn, "tasks_v1", "sla_hours"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN sla_hours INTEGER")
        if not _has_column(conn, "tasks_v1", "sla_source"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN sla_source TEXT")
        if not _has_column(conn, "tasks_v1", "assignee_team"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN assignee_team TEXT")
        if not _has_column(conn, "tasks_v1", "assigned_at"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN assigned_at TEXT")
        # Workflow 2.0: Kanban stage (ad-hoc column, does not change status CHECK)
        if not _has_column(conn, "tasks_v1", "stage"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN stage TEXT")

        # Helpful indexes (safe if columns exist)
        if not _has_column(conn, "tasks_v1", "worklist_type"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN worklist_type TEXT")
        if not _has_column(conn, "tasks_v1", "confidence"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN confidence REAL")
        if not _has_column(conn, "tasks_v1", "linked_decision_id"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN linked_decision_id TEXT")
        if not _has_column(conn, "tasks_v1", "linked_task_id"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN linked_task_id TEXT")
        if not _has_column(conn, "tasks_v1", "linked_source_facts_json"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN linked_source_facts_json TEXT NOT NULL DEFAULT '[]'")
        if not _has_column(conn, "tasks_v1", "latest_outcome_id"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN latest_outcome_id TEXT")
        if not _has_column(conn, "tasks_v1", "latest_outcome_status"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN latest_outcome_status TEXT")
        if not _has_column(conn, "tasks_v1", "latest_outcome_reason_code"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN latest_outcome_reason_code TEXT")
        if not _has_column(conn, "tasks_v1", "latest_outcome_at"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN latest_outcome_at TEXT")
        if not _has_column(conn, "tasks_v1", "latest_outcome_by"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN latest_outcome_by INTEGER")
        if not _has_column(conn, "tasks_v1", "latest_outcome_comment"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN latest_outcome_comment TEXT")
        if not _has_column(conn, "tasks_v1", "outcome_metrics_json"):
            conn.execute("ALTER TABLE tasks_v1 ADD COLUMN outcome_metrics_json TEXT NOT NULL DEFAULT '{}'" )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_domain ON tasks_v1(domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_team ON tasks_v1(assignee_team)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_stage ON tasks_v1(stage)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_worklist_type ON tasks_v1(worklist_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_linked_decision ON tasks_v1(linked_decision_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_linked_task ON tasks_v1(linked_task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_v1_latest_outcome_status ON tasks_v1(latest_outcome_status)")

    # Online schema upgrade for Audit Log 2.0 (+ archival metadata, append-only with archive mark).
    if _has_column(conn, 'audit_log', 'id'):
        _bootstrap_legacy_audit_log_schema(conn)
        _drop_audit_log_guards(conn)
        conn.execute("UPDATE audit_log SET schema_version=2 WHERE schema_version IS NULL OR schema_version < 2")
        conn.execute("UPDATE audit_log SET object_ref = CASE WHEN object_type IS NOT NULL AND object_id IS NOT NULL THEN object_type || ':' || object_id WHEN object_id IS NOT NULL THEN object_id WHEN object_type IS NOT NULL THEN object_type ELSE object_ref END WHERE COALESCE(object_ref, '') = ''")
        conn.execute("UPDATE audit_log SET action_group = CASE WHEN LOWER(COALESCE(action,'')) LIKE 'security.%' OR LOWER(COALESCE(action,'')) LIKE 'auth.%' OR LOWER(COALESCE(action,'')) LIKE 'users.%' THEN 'security' WHEN LOWER(COALESCE(action,'')) LIKE 'upload.%' OR LOWER(COALESCE(action,'')) LIKE 'connector.upload%' THEN 'upload' WHEN LOWER(COALESCE(action,'')) LIKE 'export.%' OR LOWER(COALESCE(action,'')) LIKE '%.export' OR LOWER(COALESCE(action,'')) LIKE '%.export.%' THEN 'export' WHEN LOWER(COALESCE(action,'')) LIKE 'pipeline.%' OR LOWER(COALESCE(action,'')) LIKE 'job.%' OR LOWER(COALESCE(action,'')) LIKE 'connector.%' OR LOWER(COALESCE(action,'')) LIKE '%.run' OR LOWER(COALESCE(action,'')) LIKE '%.run.%' THEN 'run' WHEN LOWER(COALESCE(action,'')) LIKE '%approve%' OR LOWER(COALESCE(action,'')) LIKE '%reject%' OR LOWER(COALESCE(action,'')) LIKE '%archive%' THEN 'approve' WHEN LOWER(COALESCE(action,'')) LIKE 'config%' OR LOWER(COALESCE(action,'')) LIKE 'configs.%' OR LOWER(COALESCE(action,'')) LIKE 'playbooks_%' OR LOWER(COALESCE(action,'')) LIKE 'price_book.%' OR LOWER(COALESCE(action,'')) LIKE 'assumptions.%' OR LOWER(COALESCE(action,'')) LIKE 'refdata.%' THEN 'config' ELSE COALESCE(NULLIF(action_group,''), 'other') END WHERE COALESCE(action_group, '') = ''")
        _ensure_audit_log_support_objects(conn)
        _ensure_users_v2_collaboration_columns(conn)
        _ensure_collaboration_notes_table(conn)

    # T13-02 Connectors: runs journal + scheduler state
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS connector_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          connector_run_id TEXT NOT NULL UNIQUE,
          tenant_id TEXT NOT NULL,
          connector_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          trigger_type TEXT NOT NULL,
          schedule_slot TEXT,
          status TEXT NOT NULL CHECK(status IN ('running','success','partial','failed','noop','stub')),
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
        CREATE INDEX IF NOT EXISTS idx_connector_runs_connector ON connector_runs(tenant_id, connector_id, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_connector_runs_status ON connector_runs(status, started_at DESC);

        CREATE TABLE IF NOT EXISTS connector_schedule_state (
          tenant_id TEXT NOT NULL,
          connector_id TEXT NOT NULL,
          last_slot TEXT,
          last_enqueued_at TEXT,
          last_job_id INTEGER,
          PRIMARY KEY(tenant_id, connector_id)
        );
        """
    )

    connector_runs_sql = _connector_runs_table_sql(conn)
    if connector_runs_sql and "'partial'" not in connector_runs_sql:
        conn.executescript(
            """
            ALTER TABLE connector_runs RENAME TO connector_runs_old_partial;
            CREATE TABLE connector_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              connector_run_id TEXT NOT NULL UNIQUE,
              tenant_id TEXT NOT NULL,
              connector_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              trigger_type TEXT NOT NULL,
              schedule_slot TEXT,
              status TEXT NOT NULL CHECK(status IN ('running','success','partial','failed','noop','stub')),
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
            INSERT INTO connector_runs(
              id, connector_run_id, tenant_id, connector_id, kind, trigger_type, schedule_slot, status, created_at, started_at, finished_at, data_version, message, config_path, outputs_json, selected_files_json, ingest_summaries_json, error_text
            )
            SELECT
              id, connector_run_id, tenant_id, connector_id, kind, trigger_type, schedule_slot, status, created_at, started_at, finished_at, data_version, message, config_path, outputs_json, selected_files_json, ingest_summaries_json, error_text
            FROM connector_runs_old_partial;
            DROP TABLE connector_runs_old_partial;
            CREATE INDEX IF NOT EXISTS idx_connector_runs_connector ON connector_runs(tenant_id, connector_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_connector_runs_status ON connector_runs(status, started_at DESC);
            """
        )


    # Online schema upgrade for T14-03 weekly plans (approval request + pdf export metadata)
    if _has_column(conn, "weekly_plans_v1", "plan_id"):
        if not _has_column(conn, "weekly_plans_v1", "approval_requested_at"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN approval_requested_at TEXT")
        if not _has_column(conn, "weekly_plans_v1", "approval_requested_by"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN approval_requested_by INTEGER")
        if not _has_column(conn, "weekly_plans_v1", "approval_requested_by_username"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN approval_requested_by_username TEXT")
        if not _has_column(conn, "weekly_plans_v1", "approval_request_comment"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN approval_request_comment TEXT")
        if not _has_column(conn, "weekly_plans_v1", "pdf_exported_at"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN pdf_exported_at TEXT")
        if not _has_column(conn, "weekly_plans_v1", "pdf_exported_by"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN pdf_exported_by INTEGER")
        if not _has_column(conn, "weekly_plans_v1", "pdf_exported_by_username"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN pdf_exported_by_username TEXT")
        if not _has_column(conn, "weekly_plans_v1", "pdf_rel_path"):
            conn.execute("ALTER TABLE weekly_plans_v1 ADD COLUMN pdf_rel_path TEXT")

    # Online schema upgrade for T11-04 what-if scenarios (additive-only)
    if _has_column(conn, "whatif_scenarios_v1", "scenario_id"):
        if not _has_column(conn, "whatif_scenarios_v1", "cloned_from_scenario_id"):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN cloned_from_scenario_id TEXT")
        if not _has_column(conn, "whatif_scenarios_v1", "archived_at"):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN archived_at TEXT")
        if not _has_column(conn, "whatif_scenarios_v1", "archived_by"):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN archived_by INTEGER")
        if not _has_column(conn, "whatif_scenarios_v1", "archived_by_username"):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN archived_by_username TEXT")
        if not _has_column(conn, "whatif_scenarios_v1", "archive_comment"):
            conn.execute("ALTER TABLE whatif_scenarios_v1 ADD COLUMN archive_comment TEXT")


    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions_v1 (
      session_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      user_id INTEGER NOT NULL,
      username TEXT NOT NULL,
      role TEXT NOT NULL,
      user_source TEXT NOT NULL DEFAULT 'users_v2',
      client_kind TEXT NOT NULL CHECK(client_kind IN ('web','android','service','unknown')) DEFAULT 'unknown',
      auth_transport TEXT NOT NULL CHECK(auth_transport IN ('cookie_session','bearer','hybrid')) DEFAULT 'bearer',
      status TEXT NOT NULL CHECK(status IN ('active','revoked','expired')) DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      last_seen_at TEXT,
      expires_at TEXT,
      refresh_expires_at TEXT,
      access_token_hash TEXT,
      refresh_token_hash TEXT,
      device_id TEXT,
      device_label TEXT,
      device_platform TEXT,
      device_app_version TEXT,
      active_farm_id TEXT,
      active_site_id TEXT,
      allowed_farm_ids_json TEXT NOT NULL DEFAULT '[]',
      allowed_site_ids_json TEXT NOT NULL DEFAULT '[]',
      metadata_json TEXT NOT NULL DEFAULT '{}',
      last_ip TEXT,
      last_user_agent TEXT,
      revoked_at TEXT,
      revoke_reason TEXT
    );
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_tenant_user ON auth_sessions_v1(tenant_id, user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_status ON auth_sessions_v1(tenant_id, status, updated_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_sessions_access_hash ON auth_sessions_v1(access_token_hash);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_sessions_refresh_hash ON auth_sessions_v1(refresh_token_hash);
        """
    )


    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auth_session_refresh_lineage_v1 (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id TEXT NOT NULL,
      previous_refresh_token_hash TEXT,
      new_refresh_token_hash TEXT,
      rotated_at TEXT NOT NULL,
      device_app_version TEXT,
      FOREIGN KEY(session_id) REFERENCES auth_sessions_v1(session_id)
    );
        CREATE INDEX IF NOT EXISTS idx_auth_refresh_lineage_session ON auth_session_refresh_lineage_v1(session_id, rotated_at DESC, id DESC);

        CREATE TABLE IF NOT EXISTS auth_failed_attempts_v1 (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      username TEXT NOT NULL,
      reason_code TEXT NOT NULL,
      created_at TEXT NOT NULL,
      ip TEXT,
      user_agent TEXT
    );
        CREATE INDEX IF NOT EXISTS idx_auth_failed_attempts_tenant_created ON auth_failed_attempts_v1(tenant_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_auth_failed_attempts_tenant_username ON auth_failed_attempts_v1(tenant_id, username, created_at DESC, id DESC);
        """
    )


    _ensure_target_dm_schema(conn)

    sync_runtime_schema_registry(
        conn,
        notes={
            'web.db': {'migration_policy': 'online-additive-and-copy-rename'},
            'web.db.audit_log': {'append_only': True},
            'web.db.jobs': {'backfilled_from_legacy': True},
            'web.db.connector_runs': {'supports_partial_status': True},
            'web.db.animal_events': {'append_only': True, 'schema': 'animal_events_v1'},
            'web.db.completion_outcomes': {'append_only': True, 'schema': 'completion_outcomes_v1'},
            'web.db.vet_protocol_executions': {'append_only': False, 'schema': 'vet_protocol_executions_v1', 'versioned_templates': True},
            'web.db.treatment_journal': {'append_only': False, 'schema': 'treatment_journal_v1', 'withdrawal_rules': 'configs/health/withdrawal_rules.yaml'},
            'web.db.drug_use_compliance': {'append_only': True, 'schema': 'drug_use_compliance_v1'},
            'web.db.worklists': {'backing_table': 'tasks_v1', 'first_class_domain_object': True, 'latest_outcome_fields': True},
            'web.db.auth_sessions': {'schema': 'auth_sessions_v1', 'runtime_state': True},
            'web.db.auth_session_refresh_lineage': {'schema': 'auth_session_refresh_lineage_v1', 'runtime_state': True},
            'web.db.auth_failed_attempts': {'schema': 'auth_failed_attempts_v1', 'runtime_state': True},
        },
    )

    conn.commit()


def create_user(conn: sqlite3.Connection, *, username: str, password_hash: str, role: str) -> None:
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at) VALUES(?,?,?,?)",
        (username, password_hash, role, utcnow_iso()),
    )
    conn.commit()


def create_user_v2(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    username: str,
    password_hash: str,
    role: str,
    external_org: str | None = None,
    collaboration_mode: str | None = None,
    allowed_farm_ids_json: str = '[]',
    allowed_site_ids_json: str = '[]',
    collaboration_flags_json: str = '{}',
) -> None:
    _ensure_users_v2_collaboration_columns(conn)
    conn.execute(
        "INSERT INTO users_v2(tenant_id, username, password_hash, role, is_active, created_at, external_org, collaboration_mode, allowed_farm_ids_json, allowed_site_ids_json, collaboration_flags_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            tenant_id,
            username,
            password_hash,
            role,
            1,
            utcnow_iso(),
            external_org,
            collaboration_mode or 'internal',
            allowed_farm_ids_json,
            allowed_site_ids_json,
            collaboration_flags_json,
        ),
    )
    conn.commit()


def get_user_by_username(conn: sqlite3.Connection, username: str, tenant_id: str = "default") -> Optional[dict[str, Any]]:
    """Resolve user by username. Prefer users_v2 if present."""
    u2 = get_user_v2_by_username(conn, tenant_id=tenant_id, username=username)
    if u2:
        return u2
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int, tenant_id: str = "default") -> Optional[dict[str, Any]]:
    """Resolve user by id. Prefer users_v2 if present."""
    u2 = get_user_v2_by_id(conn, tenant_id=tenant_id, user_id=user_id)
    if u2:
        return u2
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_v2_by_username(conn: sqlite3.Connection, *, tenant_id: str, username: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND username=? AND is_active=1",
        (tenant_id, username),
    ).fetchone()
    return dict(row) if row else None


def get_user_v2_by_id(conn: sqlite3.Connection, *, tenant_id: str, user_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND id=? AND is_active=1",
        (tenant_id, user_id),
    ).fetchone()
    return dict(row) if row else None




def list_users_v2(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    only_active: bool = True,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List users for tenant (users_v2).

    Used by Workflow 2.0 UI to select assignees by username.
    """

    where = "tenant_id=?"
    args: list[Any] = [tenant_id]
    if only_active:
        where += " AND is_active=1"
    rows = conn.execute(
        f"SELECT id, username, role, is_active, created_at, external_org, collaboration_mode, allowed_farm_ids_json, allowed_site_ids_json, collaboration_flags_json FROM users_v2 WHERE {where} ORDER BY username LIMIT ?",
        tuple(args + [int(limit)]),
    ).fetchall()
    return [dict(r) for r in rows]


def list_roles(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT role FROM roles ORDER BY role").fetchall()
    if rows:
        return [str(r[0]) for r in rows]
    return [ROLE_ADMIN, ROLE_DIRECTOR, ROLE_OPERATOR, ROLE_VET, ROLE_VIEWER, ROLE_ZOOTECH, ROLE_CONSULTANT, ROLE_PARTNER]


def get_user_v2_any_by_username(conn: sqlite3.Connection, *, tenant_id: str, username: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND username=?",
        (tenant_id, username),
    ).fetchone()
    return dict(row) if row else None


def get_user_v2_any_by_id(conn: sqlite3.Connection, *, tenant_id: str, user_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND id=?",
        (tenant_id, int(user_id)),
    ).fetchone()
    return dict(row) if row else None


def update_user_v2_role(conn: sqlite3.Connection, *, tenant_id: str, user_id: int, role: str) -> None:
    conn.execute(
        "UPDATE users_v2 SET role=? WHERE tenant_id=? AND id=?",
        (role, tenant_id, int(user_id)),
    )
    conn.commit()


def update_user_v2_password_hash(conn: sqlite3.Connection, *, tenant_id: str, user_id: int, password_hash: str) -> None:
    conn.execute(
        "UPDATE users_v2 SET password_hash=? WHERE tenant_id=? AND id=?",
        (password_hash, tenant_id, int(user_id)),
    )
    conn.commit()


def set_user_v2_active(conn: sqlite3.Connection, *, tenant_id: str, user_id: int, is_active: bool) -> None:
    conn.execute(
        "UPDATE users_v2 SET is_active=? WHERE tenant_id=? AND id=?",
        (1 if is_active else 0, tenant_id, int(user_id)),
    )
    conn.commit()


def update_user_v2_collaboration_profile(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: int,
    external_org: str | None,
    collaboration_mode: str,
    allowed_farm_ids_json: str,
    allowed_site_ids_json: str,
    collaboration_flags_json: str,
) -> None:
    _ensure_users_v2_collaboration_columns(conn)
    conn.execute(
        "UPDATE users_v2 SET external_org=?, collaboration_mode=?, allowed_farm_ids_json=?, allowed_site_ids_json=?, collaboration_flags_json=? WHERE tenant_id=? AND id=?",
        (external_org, collaboration_mode, allowed_farm_ids_json, allowed_site_ids_json, collaboration_flags_json, tenant_id, int(user_id)),
    )
    conn.commit()


def count_active_users_by_role(conn: sqlite3.Connection, *, tenant_id: str, role: str) -> int:
    row = conn.execute(
        "SELECT COUNT(1) AS c FROM users_v2 WHERE tenant_id=? AND role=? AND is_active=1",
        (tenant_id, role),
    ).fetchone()
    return int((row or {"c": 0})["c"] or 0)


def ensure_default_users(conn: sqlite3.Connection, *, hash_password_fn) -> None:
    """Legacy MVP users (admin/operator/viewer)."""
    existing = conn.execute("SELECT COUNT(1) as c FROM users").fetchone()["c"]
    if existing and int(existing) > 0:
        return

    create_user(conn, username="admin", password_hash=hash_password_fn("admin"), role="admin")
    create_user(conn, username="operator", password_hash=hash_password_fn("operator"), role="operator")
    create_user(conn, username="viewer", password_hash=hash_password_fn("viewer"), role="viewer")


def ensure_rbac_seed(conn: sqlite3.Connection) -> None:
    # roles
    for r in [ROLE_ADMIN, ROLE_DIRECTOR, ROLE_ZOOTECH, ROLE_VET, ROLE_OPERATOR, ROLE_VIEWER, ROLE_CONSULTANT, ROLE_PARTNER]:
        conn.execute("INSERT OR IGNORE INTO roles(role) VALUES(?)", (r,))

    # permissions
    for p in ALL_PERMISSIONS:
        conn.execute("INSERT OR IGNORE INTO permissions(permission) VALUES(?)", (p,))

    # role_permissions
    for role, perms in DEFAULT_ROLE_PERMISSIONS.items():
        for p in perms:
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions(role, permission) VALUES(?,?)",
                (role, p),
            )
    conn.commit()


def ensure_default_users_v2(conn: sqlite3.Connection, *, tenant_id: str, hash_password_fn) -> None:
    ensure_rbac_seed(conn)

    existing = conn.execute(
        "SELECT COUNT(1) as c FROM users_v2 WHERE tenant_id=?",
        (tenant_id,),
    ).fetchone()["c"]
    if existing and int(existing) > 0:
        return

    # Default demo accounts (change in production)
    create_user_v2(conn, tenant_id=tenant_id, username="admin", password_hash=hash_password_fn("admin"), role=ROLE_ADMIN)
    create_user_v2(conn, tenant_id=tenant_id, username="operator", password_hash=hash_password_fn("operator"), role=ROLE_OPERATOR)
    create_user_v2(conn, tenant_id=tenant_id, username="viewer", password_hash=hash_password_fn("viewer"), role=ROLE_VIEWER)
    create_user_v2(conn, tenant_id=tenant_id, username="director", password_hash=hash_password_fn("director"), role=ROLE_DIRECTOR)
    create_user_v2(conn, tenant_id=tenant_id, username="zootech", password_hash=hash_password_fn("zootech"), role=ROLE_ZOOTECH)
    create_user_v2(conn, tenant_id=tenant_id, username="vet", password_hash=hash_password_fn("vet"), role=ROLE_VET)


def get_permissions_for_role(conn: sqlite3.Connection, role: str) -> list[str]:
    rows = conn.execute(
        "SELECT permission FROM role_permissions WHERE role=? ORDER BY permission",
        (role,),
    ).fetchall()
    if rows:
        return [r[0] for r in rows]
    # fallback
    return DEFAULT_ROLE_PERMISSIONS.get(role, [])


def create_job(
    conn: sqlite3.Connection,
    *,
    kind: str,
    tenant_id: str,
    user_id: int,
    user: str,
    command: str,
    args: dict[str, Any],
    log_path: Path,
    max_attempts: int | None = None,
    retry_of_job_id: int | None = None,
    queue_name: str | None = None,
    next_attempt_at: str | None = None,
    retry_source: str | None = None,
) -> int:
    cfg = load_job_runner_config(get_settings().project_root)
    refs = infer_job_refs(kind=kind, args=args if isinstance(args, dict) else {})
    cur = conn.execute(
        """
        INSERT INTO jobs(
          public_job_id, queue_name, pipeline_key, kind, status, created_at, user, command, args_json, log_path,
          tenant_id, user_id, attempt_no, max_attempts, retry_of_job_id, next_attempt_at, retry_source, data_version, run_id, qc_run,
          model_version, scoring_run, report_version
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            new_public_job_id(),
            queue_name or cfg.queue_name_default,
            refs.get('pipeline_key') or kind,
            kind,
            'queued',
            utcnow_iso(),
            user,
            command,
            json.dumps(args, ensure_ascii=False),
            str(log_path),
            tenant_id,
            int(user_id),
            int(refs.get('attempt_no') or 0),
            max(1, int(max_attempts if max_attempts is not None else cfg.max_attempts_default)),
            retry_of_job_id,
            next_attempt_at,
            retry_source,
            refs.get('data_version'),
            refs.get('run_id'),
            refs.get('qc_run'),
            refs.get('model_version'),
            refs.get('scoring_run'),
            refs.get('report_version'),
        ),
    )
    conn.commit()
    job_id = int(cur.lastrowid)
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row:
        _maybe_enqueue_job_runtime(dict(row))
    return job_id


def mark_job_running(conn: sqlite3.Connection, job_id: int) -> bool:
    cur = conn.execute(
        "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
        (utcnow_iso(), int(job_id)),
    )
    conn.commit()
    return int(cur.rowcount or 0) > 0


def request_job_cancel(conn: sqlite3.Connection, job_id: int, *, reason: str | None = None) -> dict[str, Any] | None:
    row = conn.execute('SELECT * FROM jobs WHERE id=?', (int(job_id),)).fetchone()
    if not row:
        return None
    job = dict(row)
    status = str(job.get('status') or '')
    ts = utcnow_iso()
    if status == 'queued':
        conn.execute(
            "UPDATE jobs SET status='cancelled', cancel_requested_at=?, cancelled_at=?, finished_at=?, exit_code=?, error_text=? WHERE id=?",
            (ts, ts, ts, 130, reason or 'Cancelled by user before start', int(job_id)),
        )
    elif status == 'running':
        conn.execute(
            "UPDATE jobs SET status='cancel_requested', cancel_requested_at=?, error_text=? WHERE id=?",
            (ts, reason or 'Cancellation requested by user', int(job_id)),
        )
    conn.commit()
    row2 = conn.execute('SELECT * FROM jobs WHERE id=?', (int(job_id),)).fetchone()
    return dict(row2) if row2 else None


def mark_job_finished(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    status: str,
    exit_code: int,
    result: dict[str, Any],
    artifacts: list[str] | None = None,
    error_text: str | None = None,
) -> None:
    kv = {}
    if isinstance(result, dict):
        kv = dict(result.get("kv") or {})
    data_version = str(kv.get("data_version") or "").strip() or None
    qc_run = str(kv.get("qc_run") or "").strip() or None
    model_version = str(kv.get("model_version") or "").strip() or None
    scoring_run = str(kv.get("scoring_run") or "").strip() or None
    report_version = str(kv.get("report_version") or "").strip() or None
    run_id = str(kv.get("run_id") or report_version or scoring_run or model_version or qc_run or "").strip() or None
    conn.execute(
        """
        UPDATE jobs
        SET status=?,
            finished_at=?,
            cancelled_at=CASE WHEN ?='cancelled' THEN COALESCE(cancelled_at, ?) ELSE cancelled_at END,
            exit_code=?,
            result_json=?,
            artifacts_json=?,
            error_text=?,
            data_version=COALESCE(data_version, ?),
            qc_run=COALESCE(qc_run, ?),
            model_version=COALESCE(model_version, ?),
            scoring_run=COALESCE(scoring_run, ?),
            report_version=COALESCE(report_version, ?),
            run_id=COALESCE(run_id, ?)
        WHERE id=?
        """,
        (
            status,
            utcnow_iso(),
            status,
            utcnow_iso(),
            int(exit_code),
            json.dumps(result, ensure_ascii=False),
            json.dumps(list(artifacts or []), ensure_ascii=False),
            error_text,
            data_version,
            qc_run,
            model_version,
            scoring_run,
            report_version,
            run_id,
            int(job_id),
        ),
    )
    conn.commit()

def list_jobs(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    return list_jobs_filtered(conn, limit=limit)


def get_job(conn: sqlite3.Connection, job_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
    return dict(row) if row else None


def get_job_by_public_id(conn: sqlite3.Connection, public_job_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE public_job_id=?", (str(public_job_id),)).fetchone()
    return dict(row) if row else None


def fetch_next_queued_job(conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE status='queued' AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY id ASC LIMIT 1", (utcnow_iso(),)).fetchone()
    return dict(row) if row else None


def list_jobs_filtered(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    pipeline: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM jobs WHERE 1=1"
    args: list[Any] = []
    if status:
        raw_status = str(status).strip()
        if raw_status == "active":
            placeholders = ",".join(["?"] * len(ACTIVE_JOB_STATUSES))
            sql += f" AND status IN ({placeholders})"
            args.extend(list(ACTIVE_JOB_STATUSES))
        else:
            sql += " AND status=?"
            args.append(raw_status)
    if pipeline:
        sql += " AND (pipeline_key=? OR kind=?)"
        args.extend([str(pipeline).strip(), str(pipeline).strip()])
    if q:
        term = f"%{str(q).strip()}%"
        sql += (
            " AND (public_job_id LIKE ? OR run_id LIKE ? OR data_version LIKE ? OR command LIKE ? OR user LIKE ? "
            "OR pipeline_key LIKE ? OR kind LIKE ? OR qc_run LIKE ? OR model_version LIKE ? OR scoring_run LIKE ? "
            "OR report_version LIKE ? OR retry_source LIKE ? OR error_text LIKE ?)"
        )
        args.extend([term] * 13)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit or 200), 1000)))
    rows = conn.execute(sql, tuple(args)).fetchall()
    return [dict(r) for r in rows]


def create_retry_job(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    delay_sec: float = 0.0,
    retry_source: str = "manual",
) -> Optional[int]:
    row = conn.execute('SELECT * FROM jobs WHERE id=?', (int(job_id),)).fetchone()
    if not row:
        return None
    job = dict(row)
    args_json = str(job.get('args_json') or '{}')
    try:
        args = json.loads(args_json)
    except Exception:
        args = {}
    attempt_no = int(job.get('attempt_no') or 0) + 1
    max_attempts = max(attempt_no + 1, int(job.get('max_attempts') or 1))
    log_path = Path(str(job.get('log_path') or '')).resolve()
    suffix = '.log'
    if log_path.suffix:
        suffix = log_path.suffix
    new_log_path = log_path.with_name(f"{log_path.stem}_{retry_source}_retry{attempt_no}{suffix}")
    scheduled_for = iso_after_seconds(delay_sec) if float(delay_sec or 0.0) > 0 else None
    cur = conn.execute(
        """
        INSERT INTO jobs(
          public_job_id, queue_name, pipeline_key, kind, status, created_at, user, command, args_json, log_path,
          tenant_id, user_id, attempt_no, max_attempts, retry_of_job_id, next_attempt_at, retry_source, data_version, run_id, qc_run,
          model_version, scoring_run, report_version
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            new_public_job_id(),
            job.get('queue_name') or 'default',
            job.get('pipeline_key') or job.get('kind') or 'job',
            job.get('kind') or 'job',
            'queued',
            utcnow_iso(),
            job.get('user') or 'unknown',
            job.get('command') or '',
            json.dumps(args, ensure_ascii=False),
            str(new_log_path),
            job.get('tenant_id') or 'default',
            job.get('user_id'),
            attempt_no,
            max_attempts,
            int(job_id),
            scheduled_for,
            retry_source,
            job.get('data_version'),
            job.get('run_id'),
            job.get('qc_run'),
            job.get('model_version'),
            job.get('scoring_run'),
            job.get('report_version'),
        ),
    )
    conn.commit()
    new_job_id = int(cur.lastrowid)
    row2 = conn.execute("SELECT * FROM jobs WHERE id=?", (new_job_id,)).fetchone()
    if row2:
        _maybe_enqueue_job_runtime(dict(row2))
        try:
            broker = resolve_queue_runtime_broker()
            broker.note_retry(str((dict(row2)).get("queue_name") or "default"))
        except Exception:
            pass
    return new_job_id


def list_jobs(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    return list_jobs_filtered(conn, limit=limit)


def get_job(conn: sqlite3.Connection, job_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
    return dict(row) if row else None


def fetch_next_queued_job(conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE status='queued' AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY id ASC LIMIT 1", (utcnow_iso(),)).fetchone()
    return dict(row) if row else None



def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


def _new_session_id() -> str:
    return f"sess_{secrets.token_urlsafe(18)}"


def _new_access_token() -> str:
    return f"ga_at_{secrets.token_urlsafe(24)}"


def _new_refresh_token() -> str:
    return f"ga_rt_{secrets.token_urlsafe(32)}"


def _loads_json_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x) for x in parsed if str(x).strip()]


def _iso_after_seconds(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(seconds)))).replace(microsecond=0).isoformat()


def _is_expired_ts(value: str | None) -> bool:
    if not value:
        return False
    try:
        ts = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return False
    return ts <= datetime.now(timezone.utc)


def create_auth_session(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    user_source: str = 'users_v2',
    client_kind: str = 'unknown',
    auth_transport: str = 'bearer',
    device_id: str | None = None,
    device_label: str | None = None,
    device_platform: str | None = None,
    device_app_version: str | None = None,
    active_farm_id: str | None = None,
    active_site_id: str | None = None,
    allowed_farm_ids: list[str] | None = None,
    allowed_site_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    access_ttl_sec: int = 900,
    refresh_ttl_sec: int = 60 * 60 * 24 * 30,
) -> dict[str, Any]:
    session_id = _new_session_id()
    access_token = _new_access_token()
    refresh_token = _new_refresh_token()
    created_at = utcnow_iso()
    expires_at = _iso_after_seconds(access_ttl_sec)
    refresh_expires_at = _iso_after_seconds(refresh_ttl_sec)
    refresh_hash = _token_hash(refresh_token)
    conn.execute(
        """
        INSERT INTO auth_sessions_v1(
          session_id, tenant_id, user_id, username, role, user_source, client_kind, auth_transport,
          status, created_at, updated_at, last_seen_at, expires_at, refresh_expires_at,
          access_token_hash, refresh_token_hash, device_id, device_label, device_platform, device_app_version,
          active_farm_id, active_site_id, allowed_farm_ids_json, allowed_site_ids_json, metadata_json,
          last_ip, last_user_agent
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            str(tenant_id),
            int(user_id),
            str(username),
            str(role),
            str(user_source or 'users_v2'),
            str(client_kind or 'unknown'),
            str(auth_transport or 'bearer'),
            'active',
            created_at,
            created_at,
            created_at,
            expires_at,
            refresh_expires_at,
            _token_hash(access_token),
            refresh_hash,
            device_id,
            device_label,
            device_platform,
            device_app_version,
            active_farm_id,
            active_site_id,
            json.dumps(list(allowed_farm_ids or []), ensure_ascii=False),
            json.dumps(list(allowed_site_ids or []), ensure_ascii=False),
            json.dumps(dict(metadata or {}), ensure_ascii=False),
            ip,
            user_agent,
        ),
    )
    conn.execute(
        "INSERT INTO auth_session_refresh_lineage_v1(session_id, previous_refresh_token_hash, new_refresh_token_hash, rotated_at, device_app_version) VALUES(?,?,?,?,?)",
        (session_id, None, refresh_hash, created_at, device_app_version),
    )
    conn.commit()
    row = get_auth_session_by_id(conn, session_id=session_id)
    if not row:
        raise RuntimeError('auth_session_create_failed')
    row['access_token'] = access_token
    row['refresh_token'] = refresh_token
    row['access_ttl_sec'] = int(access_ttl_sec)
    row['refresh_ttl_sec'] = int(refresh_ttl_sec)
    return row


def get_auth_session_by_id(conn: sqlite3.Connection, *, session_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM auth_sessions_v1 WHERE session_id=?", (str(session_id),)).fetchone()
    return dict(row) if row else None


def _get_auth_session_by_token_hash(conn: sqlite3.Connection, *, field: str, token: str) -> Optional[dict[str, Any]]:
    row = conn.execute(f"SELECT * FROM auth_sessions_v1 WHERE {field}=?", (_token_hash(str(token)),)).fetchone()
    return dict(row) if row else None


def get_auth_session_by_access_token(conn: sqlite3.Connection, *, access_token: str) -> Optional[dict[str, Any]]:
    return _get_auth_session_by_token_hash(conn, field='access_token_hash', token=access_token)


def get_auth_session_by_refresh_token(conn: sqlite3.Connection, *, refresh_token: str) -> Optional[dict[str, Any]]:
    return _get_auth_session_by_token_hash(conn, field='refresh_token_hash', token=refresh_token)


def touch_auth_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    ip: str | None = None,
    user_agent: str | None = None,
    active_farm_id: str | None = None,
    active_site_id: str | None = None,
) -> Optional[dict[str, Any]]:
    now = utcnow_iso()
    conn.execute(
        """
        UPDATE auth_sessions_v1
        SET updated_at=?, last_seen_at=?, last_ip=COALESCE(?, last_ip), last_user_agent=COALESCE(?, last_user_agent),
            active_farm_id=COALESCE(?, active_farm_id), active_site_id=COALESCE(?, active_site_id)
        WHERE session_id=? AND status='active'
        """,
        (now, now, ip, user_agent, active_farm_id, active_site_id, str(session_id)),
    )
    conn.commit()
    return get_auth_session_by_id(conn, session_id=session_id)


def rotate_auth_session_tokens(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    access_ttl_sec: int = 900,
    refresh_ttl_sec: int = 60 * 60 * 24 * 30,
    ip: str | None = None,
    user_agent: str | None = None,
    device_app_version: str | None = None,
) -> Optional[dict[str, Any]]:
    access_token = _new_access_token()
    refresh_token = _new_refresh_token()
    now = utcnow_iso()
    expires_at = _iso_after_seconds(access_ttl_sec)
    refresh_expires_at = _iso_after_seconds(refresh_ttl_sec)
    current_row = get_auth_session_by_id(conn, session_id=str(session_id))
    previous_refresh_hash = current_row.get('refresh_token_hash') if current_row else None
    new_refresh_hash = _token_hash(refresh_token)
    conn.execute(
        """
        UPDATE auth_sessions_v1
        SET updated_at=?, last_seen_at=?, expires_at=?, refresh_expires_at=?,
            access_token_hash=?, refresh_token_hash=?,
            last_ip=COALESCE(?, last_ip), last_user_agent=COALESCE(?, last_user_agent),
            device_app_version=COALESCE(?, device_app_version)
        WHERE session_id=? AND status='active'
        """,
        (now, now, expires_at, refresh_expires_at, _token_hash(access_token), new_refresh_hash, ip, user_agent, device_app_version, str(session_id)),
    )
    if current_row is not None:
        conn.execute(
            "INSERT INTO auth_session_refresh_lineage_v1(session_id, previous_refresh_token_hash, new_refresh_token_hash, rotated_at, device_app_version) VALUES(?,?,?,?,?)",
            (str(session_id), previous_refresh_hash, new_refresh_hash, now, device_app_version),
        )
    conn.commit()
    row = get_auth_session_by_id(conn, session_id=session_id)
    if not row:
        return None
    row['access_token'] = access_token
    row['refresh_token'] = refresh_token
    row['access_ttl_sec'] = int(access_ttl_sec)
    row['refresh_ttl_sec'] = int(refresh_ttl_sec)
    return row


def revoke_auth_session(conn: sqlite3.Connection, *, session_id: str, reason: str = 'logout') -> None:
    conn.execute(
        """
        UPDATE auth_sessions_v1
        SET status='revoked', updated_at=?, revoked_at=?, revoke_reason=?, access_token_hash=NULL, refresh_token_hash=NULL
        WHERE session_id=? AND status='active'
        """,
        (utcnow_iso(), utcnow_iso(), str(reason or 'logout'), str(session_id)),
    )
    conn.commit()


def revoke_auth_sessions_for_user(conn: sqlite3.Connection, *, tenant_id: str, user_id: int, reason: str = 'logout_all') -> list[str]:
    rows = conn.execute(
        "SELECT session_id FROM auth_sessions_v1 WHERE tenant_id=? AND user_id=? AND status='active'",
        (str(tenant_id), int(user_id)),
    ).fetchall()
    ids = [str(row['session_id']) for row in rows]
    if ids:
        conn.execute(
            "UPDATE auth_sessions_v1 SET status='revoked', updated_at=?, revoked_at=?, revoke_reason=?, access_token_hash=NULL, refresh_token_hash=NULL WHERE tenant_id=? AND user_id=? AND status='active'",
            (utcnow_iso(), utcnow_iso(), str(reason or 'logout_all'), str(tenant_id), int(user_id)),
        )
        conn.commit()
    return ids


def list_auth_sessions_for_user(conn: sqlite3.Connection, *, tenant_id: str, user_id: int, include_revoked: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM auth_sessions_v1 WHERE tenant_id=? AND user_id=?"
    params: list[Any] = [str(tenant_id), int(user_id)]
    if not include_revoked:
        sql += " AND status='active'"
    sql += " ORDER BY updated_at DESC, created_at DESC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def list_active_auth_sessions(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: int | None = None,
    username: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM auth_sessions_v1 WHERE tenant_id=? AND status='active'"
    params: list[Any] = [str(tenant_id)]
    if user_id is not None:
        sql += " AND user_id=?"
        params.append(int(user_id))
    if username:
        sql += " AND username=?"
        params.append(str(username))
    sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def list_auth_refresh_lineage(conn: sqlite3.Connection, *, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM auth_session_refresh_lineage_v1 WHERE session_id=? ORDER BY rotated_at DESC, id DESC LIMIT ?",
        (str(session_id), max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def record_auth_failed_attempt(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    username: str,
    reason_code: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO auth_failed_attempts_v1(tenant_id, username, reason_code, created_at, ip, user_agent) VALUES(?,?,?,?,?,?)",
        (str(tenant_id or 'default'), str(username or ''), str(reason_code or 'unknown'), utcnow_iso(), ip, user_agent),
    )
    conn.commit()


def list_auth_failed_attempts(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    username: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM auth_failed_attempts_v1 WHERE tenant_id=?"
    params: list[Any] = [str(tenant_id or 'default')]
    if username:
        sql += " AND username=?"
        params.append(str(username))
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def mark_expired_auth_sessions(conn: sqlite3.Connection) -> int:
    now = utcnow_iso()
    cur = conn.execute(
        "UPDATE auth_sessions_v1 SET status='expired', updated_at=?, revoked_at=COALESCE(revoked_at, ?), revoke_reason=COALESCE(revoke_reason, 'expired'), access_token_hash=NULL WHERE status='active' AND expires_at IS NOT NULL AND expires_at < ?",
        (now, now, now),
    )
    conn.commit()
    return int(cur.rowcount or 0)
