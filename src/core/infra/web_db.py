from __future__ import annotations

import json
import os
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
        if str(settings.backend or "postgres") != "redis":
            return
        envelope = _queue_envelope_from_job_row(row)
        broker.enqueue(envelope, idempotency_key=f"job:{envelope.public_job_id}")
    except Exception:
        return


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


def create_user(conn: Any, *, username: str, password_hash: str, role: str) -> None:
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at) VALUES(?,?,?,?)",
        (username, password_hash, role, utcnow_iso()),
    )
    conn.commit()


def create_user_v2(
    conn: Any,
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


def get_user_by_username(conn: Any, username: str, tenant_id: str = "default") -> Optional[dict[str, Any]]:
    """Resolve user by username. Prefer users_v2 if present."""
    u2 = get_user_v2_by_username(conn, tenant_id=tenant_id, username=username)
    if u2:
        return u2
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: Any, user_id: int, tenant_id: str = "default") -> Optional[dict[str, Any]]:
    """Resolve user by id. Prefer users_v2 if present."""
    u2 = get_user_v2_by_id(conn, tenant_id=tenant_id, user_id=user_id)
    if u2:
        return u2
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_v2_by_username(conn: Any, *, tenant_id: str, username: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND username=? AND is_active=1",
        (tenant_id, username),
    ).fetchone()
    return dict(row) if row else None


def get_user_v2_by_id(conn: Any, *, tenant_id: str, user_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND id=? AND is_active=1",
        (tenant_id, user_id),
    ).fetchone()
    return dict(row) if row else None




def list_users_v2(
    conn: Any,
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


def list_roles(conn: Any) -> list[str]:
    rows = conn.execute("SELECT role FROM roles ORDER BY role").fetchall()
    if rows:
        return [str(r[0]) for r in rows]
    return [ROLE_ADMIN, ROLE_DIRECTOR, ROLE_OPERATOR, ROLE_VET, ROLE_VIEWER, ROLE_ZOOTECH, ROLE_CONSULTANT, ROLE_PARTNER]


def get_user_v2_any_by_username(conn: Any, *, tenant_id: str, username: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND username=?",
        (tenant_id, username),
    ).fetchone()
    return dict(row) if row else None


def get_user_v2_any_by_id(conn: Any, *, tenant_id: str, user_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM users_v2 WHERE tenant_id=? AND id=?",
        (tenant_id, int(user_id)),
    ).fetchone()
    return dict(row) if row else None


def update_user_v2_role(conn: Any, *, tenant_id: str, user_id: int, role: str) -> None:
    conn.execute(
        "UPDATE users_v2 SET role=? WHERE tenant_id=? AND id=?",
        (role, tenant_id, int(user_id)),
    )
    conn.commit()


def update_user_v2_password_hash(conn: Any, *, tenant_id: str, user_id: int, password_hash: str) -> None:
    conn.execute(
        "UPDATE users_v2 SET password_hash=? WHERE tenant_id=? AND id=?",
        (password_hash, tenant_id, int(user_id)),
    )
    conn.commit()


def set_user_v2_active(conn: Any, *, tenant_id: str, user_id: int, is_active: bool) -> None:
    conn.execute(
        "UPDATE users_v2 SET is_active=? WHERE tenant_id=? AND id=?",
        (1 if is_active else 0, tenant_id, int(user_id)),
    )
    conn.commit()


def update_user_v2_collaboration_profile(
    conn: Any,
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


def count_active_users_by_role(conn: Any, *, tenant_id: str, role: str) -> int:
    row = conn.execute(
        "SELECT COUNT(1) AS c FROM users_v2 WHERE tenant_id=? AND role=? AND is_active=1",
        (tenant_id, role),
    ).fetchone()
    return int((row or {"c": 0})["c"] or 0)


def get_permissions_for_role(conn: Any, role: str) -> list[str]:
    rows = conn.execute(
        "SELECT permission FROM role_permissions WHERE role=? ORDER BY permission",
        (role,),
    ).fetchall()
    if rows:
        return [r[0] for r in rows]
    # fallback
    return DEFAULT_ROLE_PERMISSIONS.get(role, [])


def create_job(
    conn: Any,
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


def mark_job_running(conn: Any, job_id: int) -> bool:
    cur = conn.execute(
        "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
        (utcnow_iso(), int(job_id)),
    )
    conn.commit()
    return int(cur.rowcount or 0) > 0


def request_job_cancel(conn: Any, job_id: int, *, reason: str | None = None) -> dict[str, Any] | None:
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
    conn: Any,
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

def list_jobs(conn: Any, limit: int = 200) -> list[dict[str, Any]]:
    return list_jobs_filtered(conn, limit=limit)


def get_job(conn: Any, job_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
    return dict(row) if row else None


def get_job_by_public_id(conn: Any, public_job_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE public_job_id=?", (str(public_job_id),)).fetchone()
    return dict(row) if row else None


def fetch_next_queued_job(conn: Any) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE status='queued' AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY id ASC LIMIT 1", (utcnow_iso(),)).fetchone()
    return dict(row) if row else None


def list_jobs_filtered(
    conn: Any,
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
    conn: Any,
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


def list_jobs(conn: Any, limit: int = 200) -> list[dict[str, Any]]:
    return list_jobs_filtered(conn, limit=limit)


def get_job(conn: Any, job_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
    return dict(row) if row else None


def fetch_next_queued_job(conn: Any) -> Optional[dict[str, Any]]:
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
    conn: Any,
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


def get_auth_session_by_id(conn: Any, *, session_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM auth_sessions_v1 WHERE session_id=?", (str(session_id),)).fetchone()
    return dict(row) if row else None


def _get_auth_session_by_token_hash(conn: Any, *, field: str, token: str) -> Optional[dict[str, Any]]:
    row = conn.execute(f"SELECT * FROM auth_sessions_v1 WHERE {field}=?", (_token_hash(str(token)),)).fetchone()
    return dict(row) if row else None


def get_auth_session_by_access_token(conn: Any, *, access_token: str) -> Optional[dict[str, Any]]:
    return _get_auth_session_by_token_hash(conn, field='access_token_hash', token=access_token)


def get_auth_session_by_refresh_token(conn: Any, *, refresh_token: str) -> Optional[dict[str, Any]]:
    return _get_auth_session_by_token_hash(conn, field='refresh_token_hash', token=refresh_token)


def touch_auth_session(
    conn: Any,
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
    conn: Any,
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


def revoke_auth_session(conn: Any, *, session_id: str, reason: str = 'logout') -> None:
    conn.execute(
        """
        UPDATE auth_sessions_v1
        SET status='revoked', updated_at=?, revoked_at=?, revoke_reason=?, access_token_hash=NULL, refresh_token_hash=NULL
        WHERE session_id=? AND status='active'
        """,
        (utcnow_iso(), utcnow_iso(), str(reason or 'logout'), str(session_id)),
    )
    conn.commit()


def revoke_auth_sessions_for_user(conn: Any, *, tenant_id: str, user_id: int, reason: str = 'logout_all') -> list[str]:
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


def list_auth_sessions_for_user(conn: Any, *, tenant_id: str, user_id: int, include_revoked: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM auth_sessions_v1 WHERE tenant_id=? AND user_id=?"
    params: list[Any] = [str(tenant_id), int(user_id)]
    if not include_revoked:
        sql += " AND status='active'"
    sql += " ORDER BY updated_at DESC, created_at DESC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def list_active_auth_sessions(
    conn: Any,
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


def list_auth_refresh_lineage(conn: Any, *, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM auth_session_refresh_lineage_v1 WHERE session_id=? ORDER BY rotated_at DESC, id DESC LIMIT ?",
        (str(session_id), max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def record_auth_failed_attempt(
    conn: Any,
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
    conn: Any,
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


def mark_expired_auth_sessions(conn: Any) -> int:
    now = utcnow_iso()
    cur = conn.execute(
        "UPDATE auth_sessions_v1 SET status='expired', updated_at=?, revoked_at=COALESCE(revoked_at, ?), revoke_reason=COALESCE(revoke_reason, 'expired'), access_token_hash=NULL WHERE status='active' AND expires_at IS NOT NULL AND expires_at < ?",
        (now, now, now),
    )
    conn.commit()
    return int(cur.rowcount or 0)
