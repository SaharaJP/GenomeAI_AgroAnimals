from __future__ import annotations

import json
import os
import csv
import io
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from time import perf_counter
from pathlib import Path
from typing import Optional
from types import SimpleNamespace
from urllib.parse import urlencode

import yaml

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile

from core.application import (
    build_ingest_job_request,
    build_pack_job_request,
    build_qc_job_request,
    build_report_job_request,
    build_repro_job_request,
    build_score_job_request,
    build_train_job_request,
    default_ml_config_path,
    enqueue_pipeline_job,
)
from core.infra import ArtifactsRepo, RunsRepo
from core.config import validate_startup_config_bundle
from core.common.time import utc_date, utc_date_str, utc_timestamp_compact
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import authenticate, create_authenticated_session, get_current_user, get_db, hash_password, resolve_request_auth_context
from .rbac import require_permissions
from core.audit.events import write_audit, list_audit, aggregate_audit_facets, archive_old_audit, count_archivable_audit, load_audit_retention_config, retention_cutoff_ts, validate_audit_scope
from core.infra.web_db import create_job, create_retry_job, ensure_default_users, ensure_default_users_v2, get_settings, init_db, get_job as db_get_job, get_user_by_username, list_jobs_filtered, list_users_v2, request_job_cancel, list_roles, get_user_v2_any_by_username, get_user_v2_any_by_id, update_user_v2_role, update_user_v2_password_hash, set_user_v2_active, count_active_users_by_role, create_user_v2, get_permissions_for_role
from core.workflow import (
    AlertCreate,
    DecisionCreate,
    TaskCreate,
    acknowledge_alert,
    acknowledge_alert_use_case,
    append_decision,
    append_decision_use_case,
    assign_task,
    auto_create_tasks_from_alerts,
    close_task,
    close_task_use_case,
    overdue_tasks_use_case,
    operational_summary_use_case,
    tasks_metrics_use_case,
    task_status_options,
    workflow_stage_catalog,
    workflow_team_catalog,
    workflow_listing_use_case,
    create_alert,
    create_task,
    generate_alerts_and_tasks,
    get_alert,
    get_decision,
    get_task,
    list_alerts,
    list_decisions,
    list_tasks,
    load_tasks_catalog,
    resolve_alert,
    resolve_alert_use_case,
    take_task,
    take_task_use_case,
    update_task_fields,
    update_task_use_case,
    upsert_generated_alerts,
    upsert_tasks_from_alerts,
)
from .feedback_v1 import FeedbackCreate, compute_feedback_metrics, export_feedback_dataset, list_feedback, load_feedback_cfg, record_feedback
from .whatif_scenarios_v1 import (
    WhatIfScenarioCreate,
    approve_scenario,
    attach_last_run,
    archive_scenario,
    clone_scenario,
    create_scenario,
    get_scenario,
    list_scenarios,
    reject_scenario,
    update_scenario,
)
from .whatif_reports_v1 import WhatIfReportCreate, create_report, get_report as get_whatif_report, list_reports as list_whatif_reports
from .weekly_plans_v1 import (
    WeeklyPlanCreate,
    approve_weekly_plan,
    archive_weekly_plan,
    create_weekly_plan,
    export_weekly_plan_pdf,
    get_weekly_plan,
    get_weekly_plan_tasks_map,
    get_weekly_plan_pdf_rel_path,
    list_pending_approval_weekly_plans,
    list_weekly_plans,
    reject_weekly_plan,
    request_approval_weekly_plan,
    summarize_weekly_plan,
    update_weekly_plan,
)
from .auth_boundary_v1 import router as auth_boundary_v1_router
from .reports_approvals_v1 import (
    approve_report,
    archive_report,
    get_report_approval,
    list_report_statuses,
    reject_report,
)
from .utils import (
    list_data_versions,
    list_model_entries,
    list_model_versions,
    list_qc_runs,
    list_report_versions,
    list_repro_runs,
    list_scoring_entries,
    list_scoring_runs,
    safe_join,
    save_upload_limited,
)
from .jobs_v2 import ACTIVE_JOB_STATUSES, discover_job_artifacts, is_previewable_artifact, load_job_runner_config, read_artifact_preview
from .connectors_v1 import (
    build_connector_run_view,
    catalog_with_state,
    enrich_binding_rows_with_run_history,
    enqueue_connector_job,
    get_connector_run,
    is_recovery_trigger,
    latest_recovery_decision,
    latest_retryable_run,
    list_connector_pending_jobs,
    list_connector_runs,
    schedule_due_connector_jobs,
    summarize_catalog_health,
    summarize_connector_runs,
    summarize_recovery_analytics,
)
from genomeai.connectors_v1 import connector_health_snapshot, connector_retry_policy, dataset_contract_name, default_form_bindings, describe_binding_sources, get_binding, load_connector_spec, load_connector_specs, resolve_upload_target, load_connector_state, save_connector_config, spec_to_form_dict, preview_connector_spec, cron_matches, schedule_slot_for
from genomeai.contract_precheck import validate_source_by_contract
from genomeai.ai_assistant_rag import build_fact_pack_for_assistant, load_copilot_answer_config
from genomeai.copilot_weekly_plan import build_weekly_plan_from_fact_pack, load_weekly_plan_copilot_config
from genomeai.copilot_target_resolver import (
    build_copilot_api_target,
    build_copilot_detail_actions,
    build_copilot_navigation_hints,
    build_copilot_web_target,
    parse_copilot_target,
    resolve_copilot_target_from_fact_pack,
    summarize_target_resolution,
)
from genomeai.copilot_tools import load_copilot_tools_config, resolve_section_required_permission
from genomeai.contracts import load_contracts_dir
from genomeai.contracts_catalog import build_contract_catalog
from genomeai.versioning import write_json
from .worker import JobWorker
from .observability import snapshot as obs_snapshot
from .security_matrix import SecurityMatrixConfigError, build_permission_matrix_view, load_permission_matrix
from .deploy_guard import DeployConfigError, load_web_session_secret, validate_runtime_config
from core.infra.runtime_storage import resolve_runtime_storage_settings, runtime_storage_diagnostics
from core.infra.runtime_state_storage import runtime_state_storage_diagnostics
from core.infra.queue_runtime import build_queue_runtime_summary_payload
from core.ops.production_lockdown import production_lockdown_report, internal_web_login_allowed, is_adult_profile
from core.ops.production_operability import build_production_operability_report, metrics_contract
from .rendering import render_template
from .api_boundary_v1 import router as api_boundary_v1_router
from .analytics_v1 import router as analytics_v1_router
from core.security import PermissionDenied as CorePermissionDenied, ensure_permissions as core_ensure_permissions, has_any_permission as core_has_any_permission, permission_denied_detail
from core.observability import (
    correlation_scope,
    ensure_request_id,
    get_structured_logger,
    record_request_finish,
    record_request_start,
)
from core.release import load_release_metadata, render_release_stamp


def _get_ip_ua(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


def _has_any_permission(user: dict, *permissions: str) -> bool:
    return core_has_any_permission(user.get('permissions'), *permissions)


def _best_run_id(*values: object) -> Optional[str]:
    for value in values:
        raw = str(value or '').strip()
        if raw:
            return raw
    return None


def _job_run_id(job: Optional[dict]) -> Optional[str]:
    if not job:
        return None
    return _best_run_id(
        job.get('run_id'),
        job.get('report_version'),
        job.get('scoring_run'),
        job.get('model_version'),
        job.get('qc_run'),
        job.get('public_job_id'),
    )


def _audit_pipeline_enqueue(
    conn,
    *,
    user: dict,
    job_id: int,
    kind: str,
    object_id: Optional[str] = None,
    extra_after: Optional[dict] = None,
) -> None:
    job = db_get_job(conn, int(job_id)) or {}
    after = {
        'kind': str(kind),
        'job_id': int(job_id),
        'public_job_id': job.get('public_job_id'),
        'pipeline_key': job.get('pipeline_key'),
        'queue_name': job.get('queue_name'),
        'data_version': job.get('data_version'),
        'run_id': _job_run_id(job),
        'qc_run': job.get('qc_run'),
        'model_version': job.get('model_version'),
        'scoring_run': job.get('scoring_run'),
        'report_version': job.get('report_version'),
    }
    if extra_after:
        after.update(extra_after)
    write_audit(
        conn,
        tenant_id=user.get('tenant_id', 'default'),
        user_id=int(user.get('id', 0)),
        username=user.get('username', ''),
        role=user.get('role', ''),
        action='pipeline.enqueue',
        object_type='job',
        object_id=str(object_id or job.get('public_job_id') or job_id),
        data_version=job.get('data_version'),
        run_id=_job_run_id(job),
        after=after,
        ip=None,
        user_agent=None,
        status='OK',
    )


def _scenario_run_id(row: Optional[dict]) -> Optional[str]:
    if not row:
        return None
    return _best_run_id(row.get('last_economics_run'), row.get('report_version'))

import core.security as rbac


def _require_or_403(user: dict, perm: str) -> None:
    try:
        core_ensure_permissions(user.get("permissions"), perm, role=str(user.get("role") or "") or None, operation=perm)
    except CorePermissionDenied as exc:
        raise HTTPException(status_code=403, detail=permission_denied_detail(exc)) from exc


_ALLOWED_USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _admin_redirect(message: str, *, level: str = "ok") -> RedirectResponse:
    return RedirectResponse(url=f"/admin/users?level={level}&msg={urlencode({'v': message})[2:]}", status_code=303)


def _validate_admin_username(username: str) -> str:
    value = str(username or "").strip()
    if not (3 <= len(value) <= 64):
        raise HTTPException(status_code=400, detail={"error": "invalid_username", "detail": "username должен содержать от 3 до 64 символов"})
    bad = [ch for ch in value if ch not in _ALLOWED_USERNAME_CHARS]
    if bad:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_username", "detail": f"username содержит недопустимый символ: {bad[0]!r}. Разрешены буквы, цифры, '.', '_', '-'"},
        )
    return value


def _validate_admin_password(password: str) -> str:
    value = str(password or "")
    if len(value) < 4:
        raise HTTPException(status_code=400, detail={"error": "invalid_password", "detail": "Пароль должен содержать минимум 4 символа"})
    return value


# --- T12-03 helpers: resolve and attach playbooks ---

def _resolve_farm_id_from_why(why: dict) -> str:
    try:
        fid = (why or {}).get('farm_id')
        return str(fid).strip() if fid is not None and str(fid).strip() else ''
    except Exception:
        return ''


def _get_recommended_playbook_for_task(conn, *, tenant_id: str, task: dict) -> dict | None:
    """Return active playbook for a task (farm override if farm_id known)."""
    try:
        from .playbooks_v1 import get_active_playbook
        from .alerts_v2 import get_alert

        farm_id = _resolve_farm_id_from_why(task.get('why') or {})
        if not farm_id and task.get('related_alert'):
            a = get_alert(conn, tenant_id=tenant_id, alert_id=str(task.get('related_alert')))
            if a:
                farm_id = _resolve_farm_id_from_why(a.get('why') or {})
        return get_active_playbook(
            conn,
            tenant_id=tenant_id,
            target_kind='task',
            target_type=str(task.get('task_type') or ''),
            farm_id=farm_id or None,
        )
    except Exception:
        return None


def _get_recommended_playbook_for_alert(conn, *, tenant_id: str, alert: dict) -> dict | None:
    try:
        from .playbooks_v1 import get_active_playbook

        farm_id = _resolve_farm_id_from_why(alert.get('why') or {})
        return get_active_playbook(
            conn,
            tenant_id=tenant_id,
            target_kind='alert',
            target_type=str(alert.get('alert_type') or ''),
            farm_id=farm_id or None,
        )
    except Exception:
        return None

def _resolve_cfg_path(cfg_path: str) -> Path:
    p = Path(cfg_path)
    if not p.is_absolute():
        p = (settings.project_root / p).resolve()
    return p


def _connector_configs_dir() -> Path:
    return safe_join(settings.project_root, "configs/connectors")


def _get_connector_spec_or_404(connector_id: str):
    connector_id = str(connector_id or '').strip()
    cfg_path = _config_path_for_connector_id(connector_id)
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    try:
        return load_connector_spec(cfg_path, project_root=settings.project_root)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"connector_config_invalid: {connector_id}: {e}")


def _connector_form_payload(spec=None):
    if spec is None:
        payload = {
            "connector_id": "",
            "kind": "file",
            "enabled": True,
            "description": "",
            "source_dir": "",
            "schedule": "",
            "data_version_template": "",
            "retry_policy_enabled": False,
            "retry_policy_max_attempts": 1,
            "retry_policy_backoff_sec": 60,
            "retry_policy_status_partial": True,
            "retry_policy_status_failed": False,
            "datasets": default_form_bindings(blank_rows=2),
        }
        return payload
    payload = spec_to_form_dict(spec)
    datasets = list(payload.get("datasets") or [])
    for _ in range(max(0, 2 - len(datasets))):
        datasets.append({"dataset_key": "", "pattern": "", "path": "", "mapping": "", "required": False})
    payload["datasets"] = datasets
    return payload


def _config_path_for_connector_id(connector_id: str) -> Path:
    connector_id = str(connector_id or '').strip()
    if not connector_id:
        raise ValueError("connector_id is required")
    if '/' in connector_id or '\\' in connector_id:
        raise ValueError("connector_id must not contain path separators")
    return _connector_configs_dir() / f"{connector_id}.yaml"

def _connector_form_and_bindings_from_form(form):
    mode = str(form.get("mode") or "create").strip().lower()
    original_connector_id = str(form.get("original_connector_id") or "").strip()
    connector_id = str(form.get("connector_id") or "").strip()
    kind = str(form.get("kind") or "file").strip().lower()
    enabled = str(form.get("enabled") or "").strip().lower() in {"1", "true", "on", "yes"}
    description = str(form.get("description") or "").strip()
    source_dir = str(form.get("source_dir") or "").strip()
    schedule = str(form.get("schedule") or "").strip()
    data_version_template = str(form.get("data_version_template") or "").strip()
    retry_policy_enabled = str(form.get("retry_policy_enabled") or "").strip().lower() in {"1", "true", "on", "yes"}
    retry_policy_status_partial = str(form.get("retry_policy_status_partial") or "").strip().lower() in {"1", "true", "on", "yes"}
    retry_policy_status_failed = str(form.get("retry_policy_status_failed") or "").strip().lower() in {"1", "true", "on", "yes"}
    retry_policy_max_attempts = str(form.get("retry_policy_max_attempts") or "1").strip()
    retry_policy_backoff_sec = str(form.get("retry_policy_backoff_sec") or "60").strip()
    try:
        row_count = max(1, min(int(form.get("row_count") or 0), 20))
    except Exception:
        row_count = 8
    bindings = []
    for idx in range(row_count):
        bindings.append(
            {
                "dataset_key": str(form.get(f"dataset_key_{idx}") or "").strip(),
                "pattern": str(form.get(f"pattern_{idx}") or "").strip(),
                "path": str(form.get(f"path_{idx}") or "").strip(),
                "mapping": str(form.get(f"mapping_{idx}") or "").strip(),
                "required": str(form.get(f"required_{idx}") or "").strip().lower() in {"1", "true", "on", "yes"},
            }
        )
    retry_statuses = []
    if retry_policy_status_partial:
        retry_statuses.append('partial')
    if retry_policy_status_failed:
        retry_statuses.append('failed')
    retry_policy = {
        'configured_enabled': retry_policy_enabled,
        'enabled': retry_policy_enabled,
        'max_attempts': retry_policy_max_attempts,
        'backoff_sec': retry_policy_backoff_sec,
        'retry_on_statuses': retry_statuses,
        'failed_datasets_only': True,
    }
    form_data = {
        "connector_id": connector_id,
        "kind": kind,
        "enabled": enabled,
        "description": description,
        "source_dir": source_dir,
        "schedule": schedule,
        "data_version_template": data_version_template,
        "retry_policy_enabled": retry_policy_enabled,
        "retry_policy_max_attempts": retry_policy_max_attempts,
        "retry_policy_backoff_sec": retry_policy_backoff_sec,
        "retry_policy_status_partial": retry_policy_status_partial,
        "retry_policy_status_failed": retry_policy_status_failed,
        "datasets": bindings,
    }
    return {
        "mode": mode,
        "original_connector_id": original_connector_id,
        "connector_id": connector_id,
        "kind": kind,
        "enabled": enabled,
        "description": description,
        "source_dir": source_dir,
        "schedule": schedule,
        "data_version_template": data_version_template,
        "row_count": row_count,
        "bindings": bindings,
        "retry_policy": retry_policy,
        "form_data": form_data,
    }


def _render_connector_edit(request: Request, *, user, mode: str, original_connector_id: str, form_data: dict, notice: str = "", error: str = "", preview: dict | None = None):
    return _render(
        request,
        "connectors_edit.html",
        user=user,
        active="connectors",
        mode=mode,
        original_connector_id=original_connector_id,
        form_data=form_data,
        dataset_options=sorted(["animals", "farms", "health_events", "lactations", "testday", "treatments"]),
        notice=notice,
        error=error,
        preview=preview,
    )


def _parse_manual_schedule_slot(raw_slot: str, *, connector_id: str) -> datetime:
    slot_raw = str(raw_slot or "").strip()
    if not slot_raw:
        raise ValueError(f"scheduled_slot is required for connector={connector_id}")
    try:
        dt = datetime.fromisoformat(slot_raw)
    except Exception as e:
        raise ValueError(f"scheduled_slot must be ISO datetime for connector={connector_id}: {slot_raw}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _get_governance_flag(cfg_path: str, key: str, default: bool = False) -> bool:
    """Read a boolean governance flag from economics config."""
    try:
        p = _resolve_cfg_path(cfg_path)
        if not p.exists():
            return default
        obj = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        gov = obj.get("governance") or {}
        val = gov.get(key)
        if val is None:
            return default
        return bool(val)
    except Exception:
        return default


settings = get_settings()
job_runner_cfg = load_job_runner_config(settings.project_root)
release_metadata = load_release_metadata(project_root=settings.project_root)
release_stamp = render_release_stamp(release_metadata)


def _runtime_storage_snapshot() -> dict[str, object]:
    runtime = resolve_runtime_storage_settings(
        project_root=settings.project_root,
        storage_dir=settings.storage_dir,
        sqlite_db_path=settings.db_path,
    )
    return runtime_storage_diagnostics(runtime).as_dict()


def _runtime_state_snapshot() -> dict[str, object]:
    return runtime_state_storage_diagnostics().as_dict()


def _runtime_queue_snapshot() -> dict[str, object]:
    return build_queue_runtime_summary_payload(queue_names=[str(job_runner_cfg.queue_name_default or "default")])


def _auth_runtime_snapshot() -> dict[str, object]:
    from core.infra.runtime_auth_storage import auth_storage_diagnostics
    diag = auth_storage_diagnostics(settings=settings)
    return diag.as_dict() if hasattr(diag, 'as_dict') else dict(diag or {})


def _operability_snapshot() -> dict[str, object]:
    return build_production_operability_report(settings=settings).as_dict()


def _production_lockdown_snapshot() -> dict[str, object]:
    return production_lockdown_report(settings=settings).as_dict()


def _startup() -> None:
    try:
        cfg = validate_runtime_config(settings=settings)
        validate_startup_config_bundle(settings.project_root)
    except (DeployConfigError, ValueError) as exc:
        raise RuntimeError(f"startup_config_invalid: {exc}") from exc

    storage_cfg = (cfg or {}).get("runtime_storage") or {}

    if str(storage_cfg.get("backend") or getattr(settings, "runtime_storage_backend", "sqlite")) == "sqlite":
        # Init sqlite schema + default demo users only for compat/dev/test path.
        from .db import connect as _connect
        from .playbooks_v1 import ensure_default_playbooks

        conn = _connect(settings.db_path)
        try:
            init_db(conn)
            ensure_default_users(conn, hash_password_fn=hash_password)
            ensure_default_users_v2(conn, tenant_id="default", hash_password_fn=hash_password)
            # T12-03: seed default playbooks (idempotent)
            ensure_default_playbooks(conn, tenant_id="default")
        finally:
            conn.close()

    # Start worker (disable via GENOMEAI_WEB_DISABLE_WORKER=1)
    if os.environ.get("GENOMEAI_WEB_DISABLE_WORKER") != "1":
        worker.start()

    # Start AI crons (disable via GENOMEAI_AI_CRON_ENABLED=false)
    if os.environ.get("GENOMEAI_AI_CRON_ENABLED", "true").lower() == "true":
        try:
            from web_cabinet.ai.background.morning_brief_cron import start_cron
            start_cron()
        except Exception as _cron_exc:
            import logging as _logging
            _logging.getLogger("genomeai.startup").warning(f"morning_brief cron start failed: {_cron_exc}")
        try:
            from web_cabinet.ai.background.insight_scanner_cron import start_cron as start_scanner_cron
            start_scanner_cron()
        except Exception as _cron_exc:
            import logging as _logging
            _logging.getLogger("genomeai.startup").warning(f"insight_scanner cron start failed: {_cron_exc}")


def _shutdown() -> None:
    if os.environ.get("GENOMEAI_WEB_DISABLE_WORKER") == "1":
        return
    try:
        worker.stop()
    except Exception:
        return

    try:
        from web_cabinet.ai.background.morning_brief_cron import stop_cron
        stop_cron()
    except Exception:
        pass

    try:
        from web_cabinet.ai.background.insight_scanner_cron import stop_cron as stop_scanner_cron
        stop_scanner_cron()
    except Exception:
        pass


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _startup()
    try:
        yield
    finally:
        _shutdown()


app = FastAPI(title="GenomeAI Web Cabinet (Target)", lifespan=_lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=load_web_session_secret(allow_dev_fallback=not is_adult_profile()),
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

worker = JobWorker()
web_logger = get_structured_logger("web.api")

app.include_router(auth_boundary_v1_router)
app.include_router(api_boundary_v1_router)
app.include_router(analytics_v1_router)

from web_cabinet.ai.endpoints import register_ai_routes
register_ai_routes(app)


@app.middleware("http")
async def auth_context_http_middleware(request: Request, call_next):
    request.state.auth_transport = 'anonymous'
    request.state.client_kind = 'anonymous'
    request.state.auth_session_id = None
    conn = None
    try:
        if request.headers.get('authorization') or request.session.get('auth_session_id') or request.session.get('user_id'):
            from .db import connect as _connect

            conn = _connect(settings.db_path)
            user = resolve_request_auth_context(request, conn, allow_missing=True)
            if user:
                request.state.auth_transport = str(user.get('auth_transport') or 'unknown')
                request.state.client_kind = str(user.get('client_kind') or 'unknown')
                request.state.auth_session_id = str(user.get('auth_session_id') or '') or None
    except Exception:
        request.state.auth_transport = getattr(request.state, 'auth_transport', 'anonymous')
    finally:
        if conn is not None:
            conn.close()
    return await call_next(request)


@app.middleware("http")
async def observability_http_middleware(request: Request, call_next):
    request_id = ensure_request_id(request.headers.get("x-request-id"), prefix="req")
    session = None
    try:
        session = request.session
    except Exception:
        session = None
    user_id = (session or {}).get("user_id") if isinstance(session, dict) else None
    tenant_id = (session or {}).get("tenant_id") if isinstance(session, dict) else None
    method = request.method
    path = request.url.path
    status_code = 500
    request.state.request_id = request_id
    auth_snapshot = _auth_runtime_snapshot()
    storage_snapshot = _runtime_storage_snapshot()
    queue_snapshot = _runtime_queue_snapshot()
    auth_mode = "server_session_rbac_only" if not bool(auth_snapshot.get("legacy_cookie_fallback_allowed")) else "compat_legacy_cookie_allowed"
    record_request_start(method=method, path=path)
    started = perf_counter()
    with correlation_scope(request_id=request_id, user_id=user_id, tenant_id=tenant_id, path=path, method=method, component="web.api", storage_backend=storage_snapshot.get("backend"), queue_backend=queue_snapshot.get("backend"), auth_backend=auth_snapshot.get("backend"), auth_mode=auth_mode, release_version=release_metadata.get("version")):
        web_logger.info("http.request.started", path=path, method=method)
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
        except Exception as exc:
            web_logger.error("http.request.failed", path=path, method=method, error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            duration = max(0.0, perf_counter() - started)
            record_request_finish(method=method, path=path, status_code=status_code, duration_sec=duration)
            web_logger.info("http.request.finished", path=path, method=method, status_code=status_code, duration_sec=duration)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-GenomeAI-Version"] = str(release_metadata.get("version") or "")
    response.headers["X-GenomeAI-Build-Stamp"] = str(release_metadata.get("build_stamp") or "")
    return response


# --- NFR: health & observability (T9-01) ---


@app.get("/healthz")
def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get("/readyz")
def readyz() -> PlainTextResponse:
    """Readiness: DB reachable + storage dirs writable."""
    storage_snapshot = _runtime_storage_snapshot()
    state_snapshot = _runtime_state_snapshot()
    queue_snapshot = _runtime_queue_snapshot()
    lockdown_snapshot = _production_lockdown_snapshot()
    headers = {
        "X-GenomeAI-Storage-Backend": str(storage_snapshot.get("backend") or "unknown"),
        "X-GenomeAI-Storage-Profile": str(storage_snapshot.get("profile") or "unknown"),
        "X-GenomeAI-Storage-Migration-Status": str(storage_snapshot.get("migration_status") or "unknown"),
        "X-GenomeAI-Runtime-State-Backend": str(state_snapshot.get("backend") or "unknown"),
        "X-GenomeAI-Runtime-State-Migration-Status": str(state_snapshot.get("migration_status") or "unknown"),
        "X-GenomeAI-Queue-Backend": str(queue_snapshot.get("backend") or "unknown"),
        "X-GenomeAI-Queue-Broker-Status": str(queue_snapshot.get("broker_status") or "unknown"),
        "X-GenomeAI-Production-Lockdown": "1" if bool(lockdown_snapshot.get("lockdown_active")) else "0",
        "X-GenomeAI-Internal-Web-Login": str(lockdown_snapshot.get("internal_web_login_mode") or "unknown"),
        "X-GenomeAI-Auth-Backend": str(_auth_runtime_snapshot().get("backend") or "unknown"),
        "X-GenomeAI-Auth-Mode": str(_operability_snapshot().get("observability", {}).get("runtime_labels", {}).get("auth_mode") or "unknown"),
    }
    try:
        if str(storage_snapshot.get("backend") or "sqlite") == "sqlite":
            from .db import connect as _connect

            conn = _connect(settings.db_path)
            RunsRepo(conn).ping()
            conn.close()
        # basic storage checks
        for p in [settings.storage_dir, settings.artifacts_root, settings.logs_dir]:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".readyz"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
        if os.environ.get("GENOMEAI_WEB_DISABLE_WORKER") != "1":
            if not (worker._thread and worker._thread.is_alive()):
                raise RuntimeError("worker_not_running")
        return PlainTextResponse("ready", headers=headers)
    except Exception as e:
        return PlainTextResponse(f"not_ready: {type(e).__name__}: {e}", status_code=503, headers=headers)


@app.get("/api/observability")
def api_observability(user=Depends(get_current_user)):
    """Minimal metrics snapshot for ops dashboards/alerts."""
    snap = dict(obs_snapshot() or {})
    snap["runtime_storage"] = _runtime_storage_snapshot()
    snap["runtime_state"] = _runtime_state_snapshot()
    snap["queue_runtime"] = _runtime_queue_snapshot()
    snap["production_lockdown"] = _production_lockdown_snapshot()
    return snap


@app.get("/api/runtime-storage")
def api_runtime_storage(user=Depends(get_current_user)):
    return _runtime_storage_snapshot()


@app.get("/api/runtime-state")
def api_runtime_state(user=Depends(get_current_user)):
    return _runtime_state_snapshot()


@app.get("/api/queue-runtime")
def api_queue_runtime(user=Depends(get_current_user)):
    return _runtime_queue_snapshot()


@app.get("/api/production-profile")
def api_production_profile(user=Depends(require_permissions("configs.manage"))):
    return _production_lockdown_snapshot()


@app.get("/api/metrics-contract")
def api_metrics_contract(user=Depends(require_permissions("audit.view"))):
    return metrics_contract(settings.project_root)


@app.get("/api/operability")
def api_operability(user=Depends(require_permissions("audit.view", "configs.manage"))):
    return _operability_snapshot()


@app.get("/admin/operability", response_class=HTMLResponse)
def admin_operability(request: Request, user=Depends(require_permissions("audit.view", "configs.manage"))):
    payload = _operability_snapshot()
    return HTMLResponse(
        "<html><body><h1>Production operability</h1><pre>" + json.dumps(payload, ensure_ascii=False, indent=2) + "</pre></body></html>"
    )


@app.get("/admin/production-profile", response_class=HTMLResponse)
def admin_production_profile(request: Request, user=Depends(require_permissions("configs.manage"))):
    payload = _production_lockdown_snapshot()
    return HTMLResponse(
        "<html><body><h1>Production profile diagnostics</h1><pre>" + json.dumps(payload, ensure_ascii=False, indent=2) + "</pre></body></html>"
    )


@app.get("/api/release")
def api_release_metadata():
    return dict(release_metadata, stamp=release_stamp)


def _web_primary_url(request: Request) -> str:
    override = str(os.environ.get("GENOMEAI_WEB_PUBLIC_URL") or "").strip()
    if override:
        return override
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    port = int(os.environ.get("GENOMEAI_WEB_UI_PORT", "3000"))
    return f"{scheme}://{host}:{port}"


def _render(request: Request, name: str, **ctx):
    return render_template(
        templates,
        request,
        name,
        settings=settings,
        release=release_metadata,
        release_stamp=release_stamp,
        primary_web_url=_web_primary_url(request),
        **ctx,
    )


def _job_artifact_paths(job: dict) -> list[str]:
    try:
        stored = json.loads(job.get("artifacts_json") or "[]")
    except Exception:
        stored = []
    paths = [str(x or "").strip() for x in stored if str(x or "").strip()] if isinstance(stored, list) else []
    kv: dict[str, str] = {}
    try:
        result = json.loads(job.get("result_json") or "{}")
        if isinstance(result, dict):
            kv = dict(result.get("kv") or {})
    except Exception:
        kv = {}
    discovered = discover_job_artifacts(job, project_root=settings.project_root, artifacts_root=settings.artifacts_root, kv=kv)
    for item in discovered:
        s = str(item or "").strip()
        if s and s not in paths:
            paths.append(s)
    return paths


def _virtualize_artifact_path(raw_path: str) -> tuple[str, str]:
    s = str(raw_path or "").strip()
    if not s:
        return "", ""
    if s.startswith(("artifacts/", "web_storage/", "project/")):
        return s, s
    p = Path(s)
    if p.is_absolute():
        for prefix, base in (("artifacts", settings.artifacts_root), ("web_storage", settings.storage_dir), ("project", settings.project_root)):
            try:
                rel = p.resolve().relative_to(base.resolve())
                rel_s = str(rel).lstrip("/")
                return f"{prefix}/{rel_s}", f"{prefix}/{rel_s}"
            except Exception:
                pass
    s2 = s.lstrip("/")
    return f"project/{s2}", s2


def _job_artifact_links(job: dict) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for s in _job_artifact_paths(job):
        virtual, display_path = _virtualize_artifact_path(s)
        preview_href = f"/jobs/{int(job.get('id') or 0)}/artifact-preview?path={virtual}" if virtual and is_previewable_artifact(display_path) else None
        out.append({
            "path": display_path or s,
            "href": f"/download?path={virtual}",
            "preview_href": preview_href,
            "previewable": bool(preview_href),
        })
    return out


def _copilot_target_artifact_links(source_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in source_rows:
        ref = str((row or {}).get("ref") or "").strip()
        if not ref or ref in {"NA", "nan", "None"}:
            continue
        try:
            virtual, display_path = _virtualize_artifact_path(ref)
        except Exception:
            continue
        if not virtual:
            continue
        try:
            resolved, rel = _resolve_virtual_path(virtual)
        except Exception:
            continue
        preview_href = None
        if is_previewable_artifact(rel):
            preview_href = f"/download?path={virtual}"
        out.append({
            "label": str((row or {}).get("table") or (row or {}).get("source_id") or resolved.name),
            "ref": ref,
            "path": display_path or virtual,
            "href": f"/download?path={virtual}",
            "preview_href": preview_href,
        })
    return out


def _build_copilot_resolver_context(*, request: Request, user: dict, target: str = "", data_version: str = "", section: str = "", table: str = "", metric: str = "", run_id: str = "", report_version: str = "", fact_id: str = "", source_id: str = "", request_id: str = "") -> dict[str, object]:
    try:
        parsed = parse_copilot_target(
            target=target or None,
            data_version=data_version,
            section=section,
            table=table,
            metric=metric,
            run_id=run_id,
            report_version=report_version,
            fact_id=fact_id,
            source_id=source_id,
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "copilot_target_invalid", "detail": str(e)})

    dv = str(parsed.get("data_version") or "").strip()
    if not dv:
        raise HTTPException(status_code=400, detail={"error": "copilot_target_missing_data_version", "detail": "data_version обязателен для разрешения citation target"})

    section_required_permission = resolve_section_required_permission(parsed.get("section") or "", cfg=load_copilot_tools_config())
    effective_permissions = {str(p) for p in list(user.get("permissions") or []) if str(p).strip()}
    if section_required_permission and effective_permissions and section_required_permission not in effective_permissions:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "copilot_target_forbidden",
                "detail": f"Недостаточно прав для раздела {parsed.get('section')}: нужен доступ '{section_required_permission}'.",
                "required_permission": section_required_permission,
                "section": parsed.get("section") or "",
            },
        )

    cfg = load_copilot_answer_config()
    resolver_cfg = cfg.get("resolver", {}) or {}
    period = str(resolver_cfg.get("default_period") or "daily")
    asof_date = utc_date_str()
    assistant_fact_pack = build_fact_pack_for_assistant(
        artifacts_root=settings.artifacts_root,
        data_version=dv,
        asof_date=asof_date,
        period=period,
        web_db_path=(settings.storage_dir / "web.db") if str(settings.runtime_storage_backend or "sqlite") == "sqlite" else None,
        max_rows=int(resolver_cfg.get("max_rows", 20)),
    )
    resolution = resolve_copilot_target_from_fact_pack(fact_pack=assistant_fact_pack, target=parsed)
    target_params = dict(resolution.get("target") or parsed)

    nav = build_copilot_navigation_hints(target=target_params, resolution=resolution)
    artifact_links = _copilot_target_artifact_links([dict(x) for x in (resolution.get("sources") or []) if isinstance(x, dict)])

    inline_sources: list[str] = []
    for row in (resolution.get("sources") or []):
        if not isinstance(row, dict):
            continue
        source_id_value = str(row.get("source_id") or "").strip()
        ref_value = str(row.get("ref") or "").strip()
        section_value = str(row.get("section") or "").strip()
        line = f"{source_id_value}: {ref_value}" if source_id_value else ref_value
        if section_value:
            line += f" | section={section_value}"
        inline_sources.append(line)

    same_section_facts = []
    for row in (resolution.get("same_section_facts") or []):
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item_target = {
            "data_version": dv,
            "section": str(item.get("section") or target_params.get("section") or ""),
            "metric": str(item.get("metric_name") or ""),
            "run_id": str(item.get("run_id") or target_params.get("run_id") or ""),
            "report_version": str(item.get("report_version") or target_params.get("report_version") or ""),
            "fact_id": str(item.get("fact_id") or ""),
        }
        item["web_target_href"] = build_copilot_web_target(item_target)
        same_section_facts.append(item)

    related_tables = []
    for row in (resolution.get("related_tables") or []):
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item_target = {
            "data_version": dv,
            "section": str(item.get("section") or target_params.get("section") or ""),
            "table": str(item.get("table") or ""),
            "run_id": str(item.get("run_id") or target_params.get("run_id") or ""),
            "report_version": str(item.get("report_version") or target_params.get("report_version") or ""),
            "source_id": str(item.get("table_id") or ""),
        }
        item["web_target_href"] = build_copilot_web_target(item_target)
        related_tables.append(item)

    return {
        "user": user,
        "active": "reports",
        "target": target_params,
        "raw_target": target or "",
        "web_target_href": build_copilot_web_target(target_params),
        "api_target_href": build_copilot_api_target(target_params),
        "detail_actions": build_copilot_detail_actions(target=target_params, resolution=resolution),
        "resolution": resolution,
        "resolution_summary": summarize_target_resolution(resolution),
        "navigation_hints": nav,
        "artifact_links": artifact_links,
        "source_lines": inline_sources,
        "same_section_facts": same_section_facts,
        "related_tables": related_tables,
        "fact": resolution.get("fact"),
        "table": resolution.get("table"),
        "missing_data_request": resolution.get("missing_data_request"),
    }


def _copilot_target_api_payload(ctx: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "genomeai.copilot.target_resolution.v1",
        "target": ctx.get("target") or {},
        "web_target_href": ctx.get("web_target_href") or "",
        "api_target_href": ctx.get("api_target_href") or "",
        "detail_actions": ctx.get("detail_actions") or [],
        "resolution_summary": ctx.get("resolution_summary") or "",
        "resolution": ctx.get("resolution") or {},
        "navigation_hints": ctx.get("navigation_hints") or [],
        "artifact_links": ctx.get("artifact_links") or [],
        "source_lines": ctx.get("source_lines") or [],
    }


def _job_log_text(job: dict) -> str:
    try:
        repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
        raw = repo.read_text(Path(job["log_path"]))
    except Exception:
        return "(лог недоступен)"
    tail = int(job_runner_cfg.ui_log_tail_bytes)
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) <= tail:
        return raw
    return "... <tail> ...\n" + raw_bytes[-tail:].decode("utf-8", errors="ignore")


def _read_job_log_stream(job: dict, *, cursor: int = 0, max_bytes: int | None = None) -> dict:
    path = Path(str(job.get("log_path") or ""))
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    res = repo.read_stream(path, cursor=cursor, max_bytes=int(max_bytes or job_runner_cfg.log_stream_chunk_bytes))
    return {
        "job_id": int(job.get("id") or 0),
        "log_path": str(path),
        "cursor": int(res.get("cursor") or 0),
        "next_cursor": int(res.get("next_cursor") or 0),
        "max_bytes": int(res.get("max_bytes") or 0),
        "size_bytes": int(res.get("size_bytes") or 0),
        "text": str(res.get("text") or ""),
        "is_eof": bool(res.get("is_eof")),
        "status": str(job.get("status") or ""),
    }


def _mapping_options_for_dataset(dataset_key: str) -> list[str]:
    dataset_key = str(dataset_key or '').strip().lower()
    options: list[str] = []
    candidates = [
        settings.project_root / 'configs' / 'mappings' / f'{dataset_key}_example.yaml',
        settings.project_root / 'configs' / 'mappings' / 'templates' / 'selex' / f'{dataset_key}.yaml',
        settings.project_root / 'configs' / 'mappings' / 'templates' / '1c' / f'{dataset_key}.yaml',
        settings.project_root / 'configs' / 'mappings' / 'templates' / 'excel' / f'{dataset_key}.yaml',
    ]
    for path in candidates:
        if path.exists():
            rel = str(path.resolve().relative_to(settings.project_root.resolve()))
            if rel not in options:
                options.append(rel)
    return options


def _default_upload_mapping_options() -> dict[str, list[str]]:
    return {
        'farms': _mapping_options_for_dataset('farms'),
        'animals': _mapping_options_for_dataset('animals'),
        'lactations': _mapping_options_for_dataset('lactations'),
    }


def _build_upload_page_context(*, user: dict, contract_errors: list[dict] | None = None, created_jobs: list[str] | None = None, data_version: str | None = None, notice: str | None = None) -> dict[str, object]:
    dvs = list_data_versions(settings.artifacts_root)
    example_mappings = _default_upload_mapping_options()
    return {
        'user': user,
        'active': 'upload',
        'data_versions': dvs,
        'default_dv': data_version or f"dv_{utc_timestamp_compact()}",
        'example_mappings': example_mappings,
        'contract_errors': contract_errors or [],
        'created_jobs': created_jobs or [],
        'notice': notice or '',
    }


def _contract_focus_href(dataset: str, *, source: str | None = None) -> str:
    dataset_s = str(dataset or '').strip()
    params = {'focus': dataset_s}
    if source:
        params['source'] = str(source).strip()
    return f"/contracts?{urlencode(params)}#{dataset_s}" if dataset_s else '/contracts'


def _resolve_virtual_path(path: str) -> tuple[Path, str]:
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    try:
        return repo.resolve_virtual_path(path)
    except ValueError as exc:
        detail = str(exc)
        if detail == 'empty path':
            raise HTTPException(400, 'empty path')
        raise HTTPException(400, 'unsafe path')
    except FileNotFoundError:
        raise HTTPException(404)


def _find_contract_catalog_entry(manifest: dict[str, object], dataset: str) -> dict[str, object] | None:
    dataset_norm = str(dataset or '').strip().lower()
    if not dataset_norm:
        return None
    for row in list(manifest.get('datasets') or []):
        if not isinstance(row, dict):
            continue
        if str(row.get('dataset') or '').strip().lower() == dataset_norm:
            return dict(row)
    return None


def _build_contract_validation_report_context(*, user: dict, path: str, dataset: str = '', source: str = '', data_version: str = '') -> dict[str, object]:
    resolved, virtual = _resolve_virtual_path(path)
    try:
        payload = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir).read_json_virtual(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'validation_report_read_error: {e}')
    manifest = _load_contract_catalog_manifest()
    dataset_name = str(dataset or payload.get('dataset') or '').strip()
    dataset_key = str(payload.get('dataset_key') or '').strip()
    contract_entry = _find_contract_catalog_entry(manifest, dataset_name)
    contract_href = _contract_focus_href(dataset_name) if dataset_name else '/contracts'
    download_path, _ = _virtualize_artifact_path(virtual)
    issues = [dict(x) for x in (payload.get('issues') or []) if isinstance(x, dict)]
    preview = [str(x) for x in (payload.get('preview') or []) if str(x).strip()]
    return {
        'user': user,
        'active': 'contracts',
        'report': payload,
        'report_virtual_path': virtual,
        'report_download_path': download_path or virtual,
        'issues': issues,
        'preview': preview,
        'dataset_name': dataset_name,
        'dataset_key': dataset_key,
        'source': str(source or '').strip() or 'unknown',
        'data_version': str(data_version or payload.get('data_version') or '').strip(),
        'contract_entry': contract_entry,
        'contract_href': contract_href,
    }


def _load_contract_catalog_manifest() -> dict[str, object]:
    return build_contract_catalog(
        contracts_dir=safe_join(settings.project_root, "configs/contracts"),
        catalog_path=safe_join(settings.project_root, "configs/contracts/catalog.json"),
    )


def _filter_contract_catalog_rows(
    manifest: dict[str, object],
    *,
    q: str = "",
    domain: str = "",
    status: str = "",
    source: str = "",
) -> list[dict[str, object]]:
    rows = list(manifest.get("datasets") or [])
    q_norm = str(q or "").strip().lower()
    domain_norm = str(domain or "").strip().lower()
    status_norm = str(status or "").strip().lower()
    source_norm = str(source or "").strip().lower()

    def row_matches(row: dict[str, object]) -> bool:
        if domain_norm and str(row.get("domain") or "").strip().lower() != domain_norm:
            return False
        if status_norm and str(row.get("status") or "").strip().lower() != status_norm:
            return False
        source_values = [str(x).strip().lower() for x in (row.get("source_systems") or []) if str(x).strip()]
        if source_norm and source_norm not in source_values:
            return False
        if q_norm:
            haystack_parts = [
                str(row.get("dataset") or ""),
                str(row.get("description") or ""),
                str(row.get("contract_version") or ""),
                " ".join(str(x) for x in (row.get("required_fields") or [])),
                " ".join(str(x) for x in (row.get("source_systems") or [])),
            ]
            if q_norm not in " ".join(haystack_parts).lower():
                return False
        return True

    return [row for row in rows if isinstance(row, dict) and row_matches(row)]


def _build_contract_catalog_context(
    *,
    user: dict,
    q: str = "",
    domain: str = "",
    status: str = "",
    source: str = "",
    focus: str = "",
) -> dict[str, object]:
    manifest = _load_contract_catalog_manifest()
    source_norm = str(source or "").strip().lower()
    focus_norm = str(focus or '').strip().lower()
    base_rows = _filter_contract_catalog_rows(manifest, q=q, domain=domain, status=status, source=source)
    rows: list[dict[str, object]] = []
    for row in base_rows:
        item = dict(row)
        template_rows = [dict(x) for x in (row.get("mapping_template_rows") or []) if isinstance(x, dict)]
        if source_norm:
            template_rows = [x for x in template_rows if str(x.get("source_system") or "").strip().lower() == source_norm]
        item["mapping_template_rows"] = template_rows
        item["mapping_template_count"] = len(template_rows)
        item['focus_match'] = bool(focus_norm) and str(item.get('dataset') or '').strip().lower() == focus_norm
        item['contract_href'] = _contract_focus_href(str(item.get('dataset') or ''))
        rows.append(item)
    if focus_norm:
        rows.sort(key=lambda x: (0 if x.get('focus_match') else 1, str(x.get('dataset') or '')))
    return {
        "user": user,
        "active": 'contracts',
        "catalog": manifest,
        "datasets": rows,
        "filters": {
            "q": q,
            "domain": domain,
            "status": status,
            "source": source,
            "focus": focus,
        },
        "filter_options": {
            "domains": list(manifest.get("domains") or []),
            "statuses": list(manifest.get("statuses") or []),
            "source_systems": list(manifest.get("source_systems") or []),
        },
        "filtered_count": len(rows),
    }


def _serialize_job_row(row) -> dict:
    job = dict(row)
    job["artifacts"] = _job_artifact_links(job)
    job["artifacts_count"] = len(job["artifacts"])
    return job


def _job_family_rows(conn, job_id: int) -> list[dict]:
    rows = RunsRepo(conn).list_job_family(job_id)
    return [_serialize_job_row(r) for r in rows]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/upload", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


# --- Health / Observability (T9-01) ---


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    """Liveness check.

    Should return 200 even if DB is temporarily down.
    """
    return "ok"


@app.get("/readyz", response_class=PlainTextResponse)
def readyz(conn=Depends(get_db)) -> PlainTextResponse:
    """Readiness check: DB + key dirs."""
    storage_snapshot = _runtime_storage_snapshot()
    state_snapshot = _runtime_state_snapshot()
    queue_snapshot = _runtime_queue_snapshot()
    lockdown_snapshot = _production_lockdown_snapshot()
    headers = {
        "X-GenomeAI-Storage-Backend": str(storage_snapshot.get("backend") or "unknown"),
        "X-GenomeAI-Storage-Profile": str(storage_snapshot.get("profile") or "unknown"),
        "X-GenomeAI-Storage-Migration-Status": str(storage_snapshot.get("migration_status") or "unknown"),
        "X-GenomeAI-Runtime-State-Backend": str(state_snapshot.get("backend") or "unknown"),
        "X-GenomeAI-Runtime-State-Migration-Status": str(state_snapshot.get("migration_status") or "unknown"),
        "X-GenomeAI-Queue-Backend": str(queue_snapshot.get("backend") or "unknown"),
        "X-GenomeAI-Queue-Broker-Status": str(queue_snapshot.get("broker_status") or "unknown"),
        "X-GenomeAI-Production-Lockdown": "1" if bool(lockdown_snapshot.get("lockdown_active")) else "0",
        "X-GenomeAI-Internal-Web-Login": str(lockdown_snapshot.get("internal_web_login_mode") or "unknown"),
    }
    # Ensure sqlite responds on compat path only
    if str(storage_snapshot.get("backend") or "sqlite") == "sqlite":
        RunsRepo(conn).ping()
    # Ensure storage/artifacts roots exist
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_root.mkdir(parents=True, exist_ok=True)
    return PlainTextResponse("ready", headers=headers)


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def metrics_prometheus():
    snap = obs_snapshot()
    storage_snapshot = _runtime_storage_snapshot()
    queue_snapshot = _runtime_queue_snapshot()
    backend = str(storage_snapshot.get("backend") or "unknown")
    queue_backend = str(queue_snapshot.get("backend") or "unknown")
    first_queue = dict((queue_snapshot.get("queues") or [{}])[0] or {})
    lines = [
        "# HELP genomeai_http_requests_total Total HTTP requests seen by backend API",
        "# TYPE genomeai_http_requests_total counter",
        f"genomeai_http_requests_total {int(snap.get('http_requests_total') or 0)}",
        "# HELP genomeai_http_requests_in_flight Current in-flight HTTP requests",
        "# TYPE genomeai_http_requests_in_flight gauge",
        f"genomeai_http_requests_in_flight {int(snap.get('http_in_flight') or 0)}",
        "# HELP genomeai_jobs_started_total Total jobs started",
        "# TYPE genomeai_jobs_started_total counter",
        f"genomeai_jobs_started_total {int(snap.get('jobs_started_total') or 0)}",
        "# HELP genomeai_jobs_finished_total Total jobs finished",
        "# TYPE genomeai_jobs_finished_total counter",
        f"genomeai_jobs_finished_total {int(snap.get('jobs_finished_total') or 0)}",
        "# HELP genomeai_runtime_storage_backend_info Active runtime storage backend label",
        "# TYPE genomeai_runtime_storage_backend_info gauge",
        f'genomeai_runtime_storage_backend_info{{backend="{backend}"}} 1',
        "# HELP genomeai_queue_backend_info Active queue backend label",
        "# TYPE genomeai_queue_backend_info gauge",
        f'genomeai_queue_backend_info{{backend="{queue_backend}"}} 1',
        "# HELP genomeai_queue_pending_jobs Pending jobs currently visible in queue diagnostics",
        "# TYPE genomeai_queue_pending_jobs gauge",
        f"genomeai_queue_pending_jobs {int(first_queue.get('pending_jobs') or 0)}",
        "# HELP genomeai_queue_inflight_jobs In-flight jobs currently visible in queue diagnostics",
        "# TYPE genomeai_queue_inflight_jobs gauge",
        f"genomeai_queue_inflight_jobs {int(first_queue.get('inflight_jobs') or 0)}",
        "# HELP genomeai_queue_deadletter_jobs Dead-letter jobs currently visible in queue diagnostics",
        "# TYPE genomeai_queue_deadletter_jobs gauge",
        f"genomeai_queue_deadletter_jobs {int(first_queue.get('deadletter_jobs') or 0)}",
    ]
    return "\n".join(lines) + "\n"

@app.get("/metrics")
def metrics_json(user=Depends(get_current_user)):
    """Minimal metrics endpoint (JSON) for on-prem monitoring.

    We avoid external deps (Prometheus) in MVP+; a scraper can poll JSON.
    """
    return obs_snapshot()


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if not internal_web_login_allowed():
        raise HTTPException(status_code=404, detail="auth.internal_web_login_disabled")
    return _render(request, "login.html", error=None)


@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...), conn=Depends(get_db)):
    if not internal_web_login_allowed():
        raise HTTPException(status_code=404, detail="auth.internal_web_login_disabled")
    tenant_id = request.session.get("tenant_id", "default")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    u = authenticate(conn=conn, tenant_id=tenant_id, username=username, password=password)
    if not u:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=0,
            username=username,
            role="anonymous",
            action="auth.login",
            status="FAIL",
            error="invalid_credentials",
            ip=ip,
            user_agent=ua,
            request_id=getattr(request.state, 'request_id', None),
        )
        return _render(request, "login.html", error="Неверный логин/пароль")

    session_row = create_authenticated_session(
        request=request,
        conn=conn,
        user=u,
        client_kind='web',
        issue_web_session_cookie=True,
        active_farm_id=request.session.get('active_farm'),
        active_site_id=request.session.get('active_site'),
        device_label='legacy-web-login',
        device_platform='browser',
    )

    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(u["id"]),
        username=u.get("username", username),
        role=u.get("role", ""),
        action="auth.login",
        object_type='auth_session',
        object_id=str(session_row.get('session_id') or ''),
        after={'client_kind': 'web', 'auth_transport': 'cookie_session'},
        status="OK",
        ip=ip,
        user_agent=ua,
        request_id=getattr(request.state, 'request_id', None),
    )

    return RedirectResponse(url="/upload", status_code=302)


@app.get("/logout")
def logout(request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session_id = str(user.get('auth_session_id') or '')
    if session_id:
        try:
            from core.infra.web_db import revoke_auth_session
            revoke_auth_session(conn, session_id=session_id, reason='logout')
        except Exception:
            pass
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="auth.logout",
            object_type='auth_session',
            object_id=session_id or None,
            status="OK",
            ip=ip,
            user_agent=ua,
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)




# --- JSON API (minimal) ---

@app.get("/api/jobs")
def api_jobs(
    status: Optional[str] = None,
    pipeline: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    rows = RunsRepo(conn).list_jobs_filtered(status=status, pipeline=pipeline, q=q, limit=limit, active_statuses=ACTIVE_JOB_STATUSES)
    return {"jobs": [_serialize_job_row(r) for r in rows], "filters": {"status": status, "pipeline": pipeline, "q": q, "limit": limit}}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404, detail={"error": "job_not_found", "job_id": job_id})
    return _serialize_job_row(row)


@app.get("/api/jobs/{job_id}/log")
def api_job_log(job_id: int, tail_bytes: int | None = None, user=Depends(get_current_user), conn=Depends(get_db)):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404, detail={"error": "job_not_found", "job_id": job_id})
    job = dict(row)
    path = Path(str(job.get("log_path") or ""))
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    if not path.exists() or not path.is_file():
        return {"job_id": job_id, "log_path": str(path), "size_bytes": 0, "tail_bytes": 0, "is_truncated": False, "text": ""}
    log_tail = repo.read_bytes_tail(path, max_bytes=int(tail_bytes or job_runner_cfg.ui_log_tail_bytes))
    return {
        "job_id": job_id,
        "log_path": str(path),
        "size_bytes": int(log_tail.get("size_bytes") or 0),
        "tail_bytes": int(log_tail.get("tail_bytes") or 0),
        "is_truncated": bool(log_tail.get("is_truncated")),
        "text": str(log_tail.get("text") or ""),
        "status": str(job.get("status") or ""),
    }


@app.get("/api/jobs/{job_id}/log/stream")
def api_job_log_stream(
    job_id: int,
    cursor: int = 0,
    max_bytes: int | None = None,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404, detail={"error": "job_not_found", "job_id": job_id})
    return _read_job_log_stream(dict(row), cursor=cursor, max_bytes=max_bytes)


@app.get("/api/jobs/{job_id}/artifacts")
def api_job_artifacts(job_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404, detail={"error": "job_not_found", "job_id": job_id})
    job = _serialize_job_row(row)
    return {"job_id": job_id, "artifacts": job.get("artifacts") or [], "count": int(job.get("artifacts_count") or 0)}


@app.get("/jobs/{job_id}/artifact-preview", response_class=PlainTextResponse)
def job_artifact_preview(job_id: int, path: str, user=Depends(get_current_user), conn=Depends(get_db)):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404)
    job = _serialize_job_row(row)
    allowed = {str(a.get("href") or "").split("path=", 1)[-1]: a for a in (job.get("artifacts") or [])}
    rel = (path or "").lstrip("/")
    if rel not in allowed:
        raise HTTPException(404, detail={"error": "artifact_not_found_for_job", "job_id": job_id, "path": path})
    if not allowed[rel].get("previewable"):
        raise HTTPException(409, detail={"error": "artifact_not_previewable", "job_id": job_id, "path": path})
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    try:
        _fp, _ = repo.resolve_virtual_path(rel)
    except ValueError as exc:
        detail = str(exc)
        if detail == 'empty path':
            raise HTTPException(400, 'empty path')
        raise HTTPException(400, 'unsafe path')
    except FileNotFoundError:
        raise HTTPException(404)
    text, _ = repo.preview_virtual(rel, max_bytes=int(job_runner_cfg.ui_log_tail_bytes))
    return PlainTextResponse(text)


@app.post("/api/jobs/{job_id}/cancel")
def api_job_cancel(job_id: int, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    _require_or_403(user, rbac.PERM_PIPELINE_RUN)
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404, detail={"error": "job_not_found", "job_id": job_id})
    before = dict(row)
    if str(before.get("status") or "") in ("done", "failed", "cancelled"):
        raise HTTPException(409, detail={"error": "job_not_cancellable", "job_id": job_id, "status": before.get("status")})
    after = request_job_cancel(conn, job_id, reason=f"Cancelled by {user.get('username')}")
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=user.get("tenant_id", "default"),
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="pipeline.cancel",
        object_type="job",
        object_id=str(job_id),
        data_version=before.get("data_version"),
        run_id=before.get("run_id") or before.get("report_version") or before.get("scoring_run") or before.get("qc_run"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "job": after}


@app.post("/api/jobs/{job_id}/retry")
def api_job_retry(job_id: int, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    _require_or_403(user, rbac.PERM_PIPELINE_RUN)
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404, detail={"error": "job_not_found", "job_id": job_id})
    before = dict(row)
    if str(before.get("status") or "") not in ("failed", "cancelled"):
        raise HTTPException(409, detail={"error": "job_not_retryable", "job_id": job_id, "status": before.get("status")})
    new_job_id = create_retry_job(conn, job_id)
    if new_job_id is None:
        raise HTTPException(500, detail={"error": "retry_create_failed", "job_id": job_id})
    after = db_get_job(conn, new_job_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=user.get("tenant_id", "default"),
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="pipeline.retry",
        object_type="job",
        object_id=str(new_job_id),
        data_version=before.get("data_version"),
        run_id=before.get("run_id") or before.get("report_version") or before.get("scoring_run") or before.get("qc_run"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "job": after}


@app.post("/jobs/{job_id}/cancel")
def job_cancel_post(job_id: int, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    api_job_cancel(job_id, request, user=user, conn=conn)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/retry")
def job_retry_post(job_id: int, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    js = api_job_retry(job_id, request, user=user, conn=conn)
    new_job = js.get("job") or {}
    return RedirectResponse(url=f"/jobs/{new_job.get('id', job_id)}", status_code=303)


@app.get("/api/versions")
def api_versions(user=Depends(get_current_user)):
    dvs = list_data_versions(settings.artifacts_root)
    return {"data_versions": dvs}


# ---- Alerts v2 API ----


@app.get("/api/alerts_v2")
def api_alerts_v2_list(
    request: Request,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    source: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    q: Optional[str] = None,
    include_playbook: bool = False,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions("alerts.view")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    res = list_alerts(
        conn,
        tenant_id=tenant_id,
        status=status,
        alert_type=alert_type,
        source=source,
        owner_user_id=owner_user_id,
        object_type=object_type,
        object_id=object_id,
        q=q,
        limit=limit,
        offset=offset,
    )

    if include_playbook:
        for a in list(res.get("alerts") or []):
            pb = _get_recommended_playbook_for_alert(conn, tenant_id=tenant_id, alert=a)
            if pb:
                a["playbook_name"] = pb.get("name")
                a["playbook_version_id"] = pb.get("version_id")
            else:
                a["playbook_name"] = None
                a["playbook_version_id"] = None

    # audit as view (optional, light)
    try:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="alerts_v2.list",
            object_type="alerts_v2",
            object_id="alerts_v2",
            after={"count": len(res.get("alerts") or []), "include_playbook": bool(include_playbook)},
            ip=ip,
            user_agent=ua,
            status="OK",
        )
    except Exception:
        pass

    return res


@app.get("/api/alerts_v2/{alert_id}")
def api_alerts_v2_get(
    alert_id: str,
    include_playbook: bool = False,
    user=Depends(require_permissions("alerts.view")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    a = get_alert(conn, tenant_id=tenant_id, alert_id=alert_id)
    if not a:
        raise HTTPException(404)

    if include_playbook:
        pb = _get_recommended_playbook_for_alert(conn, tenant_id=tenant_id, alert=a)
        a["playbook"] = pb
        a["playbook_version_id"] = (pb.get("version_id") if pb else None)
    return a


@app.post("/api/alerts_v2")
async def api_alerts_v2_create(
    request: Request,
    user=Depends(require_permissions("alerts.create")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    try:
        a = AlertCreate(
            alert_type=str(body.get("alert_type")),
            title=str(body.get("title")),
            source=str(body.get("source")),
            cause=str(body.get("cause")),
            confidence=(float(body.get("confidence")) if body.get("confidence") is not None else None),
            object_type=str(body.get("object_type")),
            object_id=str(body.get("object_id")),
            deadline=(str(body.get("deadline")) if body.get("deadline") else None),
            owner_user_id=(int(body.get("owner_user_id")) if body.get("owner_user_id") is not None else None),
            attachments=list(body.get("attachments") or []),
            why=dict(body.get("why") or {}),
            what_to_do=list(body.get("what_to_do") or []),
            data_version=(str(body.get("data_version")) if body.get("data_version") else None),
            qc_run=(str(body.get("qc_run")) if body.get("qc_run") else None),
            model_version=(str(body.get("model_version")) if body.get("model_version") else None),
            scoring_run=(str(body.get("scoring_run")) if body.get("scoring_run") else None),
            report_version=(str(body.get("report_version")) if body.get("report_version") else None),
            dedupe_key=(str(body.get("dedupe_key")) if body.get("dedupe_key") else None),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "message": str(e)})

    alert_id = create_alert(conn, tenant_id=tenant_id, a=a)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="alerts_v2.create",
        object_type="alert_v2",
        object_id=alert_id,
        after={"alert_type": a.alert_type, "object": [a.object_type, a.object_id]},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"alert_id": alert_id}


@app.post("/api/alerts_v2/generate")
def api_alerts_v2_generate(
    request: Request,
    data_version: str,
    user=Depends(require_permissions("alerts.generate")),
    conn=Depends(get_db),
):
    """Generate alerts from QC/ML/business rules and upsert into alerts_v2."""
    tenant_id = user.get("tenant_id", "default")
    ip, ua = _get_ip_ua(request)

    generation = generate_alerts_and_tasks(
        conn=conn,
        tenant_id=tenant_id,
        data_version=str(data_version),
        artifacts_root=settings.artifacts_root,
        project_root=settings.project_root,
    )
    inserted = int(generation.get("inserted") or 0)
    updated = int(generation.get("updated") or 0)
    auto_tasks = dict(generation.get("auto_tasks") or {})
    candidates_count = int(generation.get("candidates") or 0)

    # Audit summary for auto-tasking (critical action). Per-task audits are optional and capped.
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="tasks_v1.auto_create.summary",
            object_type="data_version",
            object_id=str(data_version),
            data_version=str(data_version),
            after={
                "eligible": int(auto_tasks.get("eligible") or 0),
                "inserted": int(auto_tasks.get("inserted") or 0),
                "skipped": int(auto_tasks.get("skipped") or 0),
                "task_ids": list(auto_tasks.get("task_ids") or [])[:10],
            },
            ip=ip,
            user_agent=ua,
            status="OK",
        )
    except Exception:
        pass

    # Audit each auto-created task (capped)
    try:
        for _tid in list(auto_tasks.get('task_ids') or [])[:50]:
            _t = get_task(conn, tenant_id=tenant_id, task_id=str(_tid)) or {}
            write_audit(
                conn,
                tenant_id=tenant_id,
                user_id=int(user.get('id', 0)),
                username=user.get('username', ''),
                role=user.get('role', ''),
                action='tasks_v1.auto_create',
                object_type='task_v1',
                object_id=str(_tid),
                data_version=str(_t.get('data_version') or data_version),
                after={
                    'task_type': _t.get('task_type'),
                    'domain': _t.get('domain'),
                    'priority': _t.get('priority'),
                    'related_alert': _t.get('related_alert'),
                    'object': [_t.get('object_type'), _t.get('object_id')],
                },
                ip=ip,
                user_agent=ua,
                status='OK',
            )
    except Exception:
        pass

    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="alerts_v2.generate",
        object_type="data_version",
        object_id=str(data_version),
        data_version=str(data_version),
        after={"inserted": inserted, "updated": updated, "candidates": candidates_count, "auto_tasks": {k: auto_tasks.get(k) for k in ("eligible","inserted","skipped")}},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"candidates": candidates_count, "inserted": inserted, "updated": updated, "auto_tasks": auto_tasks}


@app.post("/api/alerts_v2/{alert_id}/ack")
def api_alerts_v2_ack(
    alert_id: str,
    request: Request,
    user=Depends(require_permissions("alerts.ack")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    try:
        res = acknowledge_alert_use_case(conn=conn, tenant_id=tenant_id, alert_id=alert_id, user_id=int(user.get("id", 0)))
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(status_code=409, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="alerts_v2.ack",
        object_type="alert_v2",
        object_id=alert_id,
        ip=ip,
        user_agent=ua,
        after={"status": res.get("status")},
        status="OK",
    )
    return {"ok": True}


@app.post("/api/alerts_v2/{alert_id}/resolve")
async def api_alerts_v2_resolve(
    alert_id: str,
    request: Request,
    user=Depends(require_permissions("alerts.resolve")),
    conn=Depends(get_db),
):
    body = await request.json()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail={"error": "reason_required"})

    tenant_id = user.get("tenant_id", "default")
    try:
        res = resolve_alert_use_case(conn=conn, tenant_id=tenant_id, alert_id=alert_id, user_id=int(user.get("id", 0)), reason=reason)
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="alerts_v2.resolve",
        object_type="alert_v2",
        object_id=alert_id,
        after={"status": res.get("status"), "reason": res.get("reason")},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


# ---- Decision Log v2 API ----


@app.get("/api/decision_log_v2")
def api_decision_log_v2_list(
    farm_id: Optional[str] = None,
    group_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    related_alert: Optional[str] = None,
    recommendation_id: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    data_version: Optional[str] = None,
    model_version: Optional[str] = None,
    report_version: Optional[str] = None,
    q: Optional[str] = None,
    include_playbook: bool = False,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions("decisionlog.view")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    return list_decisions(
        conn,
        tenant_id=tenant_id,
        farm_id=farm_id,
        group_id=group_id,
        object_type=object_type,
        object_id=object_id,
        related_alert=related_alert,
        recommendation_id=recommendation_id,
        action=action,
        user_id=user_id,
        data_version=data_version,
        model_version=model_version,
        report_version=report_version,
        q=q,
        limit=int(limit),
        offset=int(offset),
    )


@app.get("/api/decision_log_v2/{decision_id}")
def api_decision_log_v2_get(
    decision_id: str,
    user=Depends(require_permissions("decisionlog.view")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    d = get_decision(conn, tenant_id=tenant_id, decision_id=decision_id)
    if not d:
        raise HTTPException(404)
    return d


@app.post("/api/decision_log_v2")
async def api_decision_log_v2_append(
    request: Request,
    user=Depends(require_permissions("decisionlog.write")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    action = str(body.get("action") or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail={"error": "action_required"})

    d = DecisionCreate(
        recommendation_id=(str(body.get("recommendation_id")) if body.get("recommendation_id") else None),
        action=action,
        user_id=int(user.get("id", 0)),
        username=str(user.get("username", "")),
        reason=(str(body.get("reason")) if body.get("reason") else None),
        comment=(str(body.get("comment")) if body.get("comment") else None),
        related_alert=(str(body.get("related_alert")) if body.get("related_alert") else None),
        object_type=(str(body.get("object_type")) if body.get("object_type") else None),
        object_id=(str(body.get("object_id")) if body.get("object_id") else None),
        farm_id=(str(body.get("farm_id")) if body.get("farm_id") else None),
        group_id=(str(body.get("group_id")) if body.get("group_id") else None),
        data_version=(str(body.get("data_version")) if body.get("data_version") else None),
        model_version=(str(body.get("model_version")) if body.get("model_version") else None),
        report_version=(str(body.get("report_version")) if body.get("report_version") else None),
        qc_run=(str(body.get("qc_run")) if body.get("qc_run") else None),
        scoring_run=(str(body.get("scoring_run")) if body.get("scoring_run") else None),
        metadata=dict(body.get("metadata") or {}),
    )

    res = append_decision_use_case(conn=conn, tenant_id=tenant_id, d=d)
    decision_id = str(res.get("decision_id"))
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="decision_log_v2.append",
        object_type="decision_log_v2",
        object_id=decision_id,
        data_version=d.data_version,
        after={"action": d.action, "related_alert": d.related_alert, "object": [d.object_type, d.object_id]},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"decision_id": decision_id}


# ---- T14-05 Feedback loop API ----


@app.get("/api/feedback_v1/config")
def api_feedback_v1_config(user=Depends(get_current_user)):
    if not _has_any_permission(user, "decisionlog.view", "tasks.view", "recommendations.confirm", "decisionlog.write", "decisions.write"):
        raise HTTPException(status_code=403)
    return load_feedback_cfg()


@app.post("/api/feedback_v1")
async def api_feedback_v1_create(
    request: Request,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    if not _has_any_permission(user, "recommendations.confirm", "decisionlog.write", "decisions.write"):
        raise HTTPException(status_code=403)
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    try:
        res = record_feedback(
            conn,
            tenant_id=tenant_id,
            fc=FeedbackCreate(
                recommendation_id=(str(body.get("recommendation_id")) if body.get("recommendation_id") else None),
                decision=str(body.get("decision") or "").strip().lower(),
                reason_code=str(body.get("reason_code") or "").strip(),
                comment=(str(body.get("comment")) if body.get("comment") else None),
                related_alert=(str(body.get("related_alert")) if body.get("related_alert") else None),
                task_id=(str(body.get("task_id")) if body.get("task_id") else None),
                object_type=(str(body.get("object_type")) if body.get("object_type") else None),
                object_id=(str(body.get("object_id")) if body.get("object_id") else None),
                farm_id=(str(body.get("farm_id")) if body.get("farm_id") else None),
                group_id=(str(body.get("group_id")) if body.get("group_id") else None),
                data_version=(str(body.get("data_version")) if body.get("data_version") else None),
                model_version=(str(body.get("model_version")) if body.get("model_version") else None),
                report_version=(str(body.get("report_version")) if body.get("report_version") else None),
                qc_run=(str(body.get("qc_run")) if body.get("qc_run") else None),
                scoring_run=(str(body.get("scoring_run")) if body.get("scoring_run") else None),
                recommendation_created_at=(str(body.get("recommendation_created_at")) if body.get("recommendation_created_at") else None),
                feedback_source=(str(body.get("feedback_source")) if body.get("feedback_source") else None),
                metadata=dict(body.get("metadata") or {}),
            ),
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            decision_reason=(str(body.get("reason")) if body.get("reason") else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action=f"feedback.{res.get('decision')}",
        object_type=str(body.get("object_type") or "recommendation"),
        object_id=str(body.get("object_id") or body.get("recommendation_id") or res.get("recommendation_id") or ""),
        data_version=(str(body.get("data_version")) if body.get("data_version") else None),
        run_id=_best_run_id(body.get("scoring_run"), body.get("report_version"), body.get("recommendation_id"), res.get("feedback_id")),
        after=res,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return res


@app.get("/api/feedback_v1")
def api_feedback_v1_list(
    recommendation_id: Optional[str] = None,
    decision: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    if not _has_any_permission(user, "decisionlog.view", "tasks.view", "audit.view"):
        raise HTTPException(status_code=403)
    tenant_id = user.get("tenant_id", "default")
    return list_feedback(
        conn,
        tenant_id=tenant_id,
        recommendation_id=recommendation_id,
        decision=decision,
        object_type=object_type,
        object_id=object_id,
        data_version=data_version,
        scoring_run=scoring_run,
        report_version=report_version,
        feedback_source=feedback_source,
        model_version=model_version,
        limit=int(limit),
        offset=int(offset),
    )


@app.get("/api/feedback_v1/metrics")
def api_feedback_v1_metrics(
    request: Request,
    window_days: Optional[int] = None,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    if not _has_any_permission(user, "decisionlog.view", "tasks.view", "audit.view"):
        raise HTTPException(status_code=403)
    tenant_id = user.get("tenant_id", "default")
    run_id = uuid.uuid4().hex
    res = compute_feedback_metrics(
        conn,
        tenant_id=tenant_id,
        window_days=window_days,
        data_version=data_version,
        scoring_run=scoring_run,
        report_version=report_version,
        feedback_source=feedback_source,
        model_version=model_version,
    )
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="feedback.metrics_view",
        object_type="feedback_metrics",
        object_id=(str(scoring_run or report_version or data_version) if (scoring_run or report_version or data_version) else "all"),
        data_version=data_version,
        run_id=run_id,
        after={
            "rows": res.get("rows"),
            "window_days": (res.get("metrics") or {}).get("window_days"),
            "filters": res.get("filters") or {},
        },
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"run_id": run_id, **res}


@app.get("/api/feedback_v1/export.csv")
def api_feedback_v1_export_csv(
    request: Request,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    if not _has_any_permission(user, "export.download", "decisionlog.view", "tasks.view"):
        raise HTTPException(status_code=403)
    tenant_id = user.get("tenant_id", "default")
    feedback_run = uuid.uuid4().hex
    res = export_feedback_dataset(
        conn,
        artifacts_root=settings.artifacts_root,
        tenant_id=tenant_id,
        feedback_run=feedback_run,
        data_version=data_version,
        scoring_run=scoring_run,
        report_version=report_version,
        feedback_source=feedback_source,
        model_version=model_version,
    )
    csv_path = Path(res["outputs"]["feedback_dataset_csv"])
    payload = csv_path.read_bytes()
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="feedback.export",
        object_type="feedback_dataset",
        object_id=feedback_run,
        data_version=data_version,
        run_id=feedback_run,
        after={**res, "filters": {"data_version": data_version, "scoring_run": scoring_run, "report_version": report_version, "feedback_source": feedback_source, "model_version": model_version}},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    filename = f"feedback_dataset_{feedback_run}.csv"
    resp = StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["X-Run-Id"] = feedback_run
    return resp


# ---- Tasks / Worklists v1 API ----


@app.get("/api/workflow_v2/teams")
def api_workflow_v2_teams(
    user=Depends(require_permissions("tasks.view")),
):
    """Return configured teams catalog (Workflow 2.0)."""

    return {"teams": list((workflow_team_catalog() or {}).get("teams") or [])}


@app.get("/api/workflow_v2/stages")
def api_workflow_v2_stages(
    user=Depends(require_permissions("tasks.view")),
):
    """Return configured stages (Kanban columns) for Workflow 2.0."""

    cfg = workflow_stage_catalog() or {}
    return {
        "default_stage_open": str(cfg.get("default_stage_open") or "triage"),
        "stages": list(cfg.get("stages") or []),
        "done_stage": str(cfg.get("done_stage") or "done"),
        "cancelled_stage": str(cfg.get("cancelled_stage") or "cancelled"),
    }




@app.get("/api/users_v2")
def api_users_v2_list(
    limit: int = 200,
    user=Depends(require_permissions("tasks.write")),
    conn=Depends(get_db),
):
    """List active users for assignment dropdowns (Workflow 2.0)."""

    tenant_id = user.get("tenant_id", "default")
    try:
        users = list_users_v2(conn, tenant_id=tenant_id, only_active=True, limit=int(limit or 200))
        return {
            "users": [
                {"id": int(u.get("id")), "username": u.get("username"), "role": u.get("role")}
                for u in users
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "users_list_failed", "detail": str(e)[:300]})

@app.get("/api/tasks_v1")
def api_tasks_v1_list(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    owner_username: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
    overdue_only: bool = False,
    related_alert: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    due_before: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    include_playbook: bool = False,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions("tasks.view")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")

    # Convenience: filter by username (UI-friendly)
    if owner_user_id is None and owner_username:
        u = get_user_by_username(conn, username=str(owner_username).strip(), tenant_id=tenant_id)
        if not u:
            raise HTTPException(status_code=400, detail={"error": "invalid_owner_username", "hint": str(owner_username)})
        owner_user_id = int(u.get("id"))

    try:
        res = list_tasks(
            conn,
            tenant_id=tenant_id,
            status=status,
            task_type=task_type,
            owner_user_id=owner_user_id,
            domain=domain,
            stage=stage,
            assignee_team=assignee_team,
            overdue_only=bool(overdue_only),
            related_alert=related_alert,
            object_type=object_type,
            object_id=object_id,
            due_before=due_before,
            q=q,
            limit=int(limit),
            offset=int(offset),
        )

        if include_playbook:
            # Attach minimal playbook info for UI. Avoid large payloads by not embedding full steps.
            for t in list(res.get("tasks") or []):
                pb = _get_recommended_playbook_for_task(conn, tenant_id=tenant_id, task=t)
                if pb:
                    t["playbook_name"] = pb.get("name")
                    t["playbook_version_id"] = pb.get("version_id")
                else:
                    t["playbook_name"] = None
                    t["playbook_version_id"] = None

        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)[:500]})


@app.get("/api/tasks_v1/export")
def api_tasks_v1_export(
    request: Request,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    owner_username: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
    overdue_only: bool = False,
    related_alert: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    due_before: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 5000,
    user=Depends(require_permissions("tasks.view")),
    conn=Depends(get_db),
):
    """Export filtered tasks list as CSV.

    Notes:
      - CSV is a *view* action, but we still audit it as it often leaves the system perimeter.
      - We cap export rows to avoid accidental huge responses.
    """

    tenant_id = user.get("tenant_id", "default")
    run_id = uuid.uuid4().hex

    # Convenience: filter by username (UI-friendly)
    if owner_user_id is None and owner_username:
        u = get_user_by_username(conn, username=str(owner_username).strip(), tenant_id=tenant_id)
        if not u:
            raise HTTPException(status_code=400, detail={"error": "invalid_owner_username", "hint": str(owner_username)})
        owner_user_id = int(u.get("id"))

    try:
        lim = int(limit or 0)
    except Exception:
        lim = 5000
    lim = max(1, min(20000, lim))

    try:
        res = list_tasks(
            conn,
            tenant_id=tenant_id,
            status=status,
            task_type=task_type,
            owner_user_id=owner_user_id,
            domain=domain,
            stage=stage,
            assignee_team=assignee_team,
            overdue_only=bool(overdue_only),
            related_alert=related_alert,
            object_type=object_type,
            object_id=object_id,
            due_before=due_before,
            q=q,
            limit=lim,
            offset=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)[:500]})
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="tasks_v1.export",
            object_type="tasks_v1_export",
            object_id="tasks_v1",
            run_id=run_id,
            ip=ip,
            user_agent=ua,
            status="ERROR",
            error=str(e)[:500],
        )
        raise

    tasks = list(res.get("tasks") or [])
    out = io.StringIO()
    # Keep columns stable for downstream Excel/BI.
    cols = [
        "task_id",
        "created_at",
        "updated_at",
        "status",
        "stage",
        "domain",
        "task_type",
        "title",
        "priority",
        "owner_user_id",
        "owner_username",
        "assignee_team",
        "due_at",
        "is_overdue",
        "closed_at",
        "closed_reason",
        "related_alert",
        "object_type",
        "object_id",
        "data_version",
        "qc_run",
        "model_version",
        "scoring_run",
        "report_version",
    ]
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for t in tasks:
        try:
            w.writerow({k: t.get(k) for k in cols})
        except Exception:
            # best-effort row write
            w.writerow({"task_id": t.get("task_id"), "title": t.get("title")})

    payload = out.getvalue()
    ts = utc_timestamp_compact()
    filename = f"tasks_v1_export_{ts}.csv"

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.export",
        object_type="tasks_v1_export",
        object_id="tasks_v1",
        run_id=run_id,
        after={
            "count": len(tasks),
            "status": status,
            "task_type": task_type,
            "owner_user_id": owner_user_id,
            "domain": domain,
            "stage": stage,
            "assignee_team": assignee_team,
            "overdue_only": bool(overdue_only),
            "q": q,
            "limit": lim,
        },
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    resp = StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["X-Run-Id"] = run_id
    return resp

@app.get("/api/tasks_v1/metrics")
def api_tasks_v1_metrics(
    request: Request,
    window_days: Optional[int] = None,
    user=Depends(require_permissions("tasks.view")),
    conn=Depends(get_db),
):
    """Director metrics for tasks execution (lead time / overdue rate)."""

    tenant_id = user.get("tenant_id", "default")
    run_id = uuid.uuid4().hex

    try:
        metrics_payload = tasks_metrics_use_case(conn=conn, tenant_id=tenant_id, window_days=window_days)
        metrics = dict(metrics_payload.get("metrics") or {})
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="tasks_v1.metrics_view",
            object_type="tasks_v1_metrics",
            object_id="tasks_v1",
            run_id=run_id,
            ip=ip,
            user_agent=ua,
            status="ERROR",
            error=str(e)[:500],
        )
        raise

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.metrics_view",
        object_type="tasks_v1_metrics",
        object_id="tasks_v1",
        run_id=run_id,
        after={"window_days": metrics.get("window_days"), "active_total": metrics.get("active_total"), "overdue_rate": metrics.get("overdue_rate_active")},
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    return {"run_id": run_id, "metrics": metrics}



@app.get("/api/tasks_v1/overdue")
def api_tasks_v1_overdue(
    request: Request,
    limit: int = 20,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
    user=Depends(require_permissions("tasks.view")),
    conn=Depends(get_db),
):
    """Return top overdue active tasks for quick director review."""

    tenant_id = user.get("tenant_id", "default")
    run_id = uuid.uuid4().hex

    try:
        overdue_payload = overdue_tasks_use_case(
            conn=conn,
            tenant_id=tenant_id,
            limit=int(limit or 20),
            domain=(domain or None),
            assignee_team=(assignee_team or None),
        )
        items = list(overdue_payload.get("items") or [])
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="tasks_v1.overdue_view",
            object_type="tasks_v1_overdue",
            object_id="tasks_v1",
            run_id=run_id,
            ip=ip,
            user_agent=ua,
            status="ERROR",
            error=str(e)[:500],
        )
        raise

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.overdue_view",
        object_type="tasks_v1_overdue",
        object_id="tasks_v1",
        run_id=run_id,
        after={"limit": int(limit or 20), "count": len(items), "domain": domain, "assignee_team": assignee_team},
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    return {"run_id": run_id, "items": items}


@app.get("/api/tasks_v1/{task_id}")
def api_tasks_v1_get(
    task_id: str,
    user=Depends(require_permissions("tasks.view")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    t = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    if not t:
        raise HTTPException(404)

    # T12-03: attach recommended playbook
    pb = _get_recommended_playbook_for_task(conn, tenant_id=tenant_id, task=t)
    if pb:
        t["playbook"] = pb
        t["playbook_version_id"] = pb.get("version_id")
    else:
        t["playbook"] = None
        t["playbook_version_id"] = None
    return t




@app.post("/api/tasks_v1")
async def api_tasks_v1_create(
    request: Request,
    user=Depends(require_permissions("tasks.write")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    task_type = str(body.get("task_type") or "").strip()
    title = str(body.get("title") or "").strip()
    if not task_type or not title:
        raise HTTPException(status_code=400, detail={"error": "task_type_and_title_required"})

    t = TaskCreate(
        task_type=task_type,
        title=title,
        domain=(str(body.get("domain")) if body.get("domain") else None),
        priority=int(body.get("priority") or 3),
        due_at=(str(body.get("due_at")) if body.get("due_at") else None),
        owner_user_id=(int(body.get("owner_user_id")) if body.get("owner_user_id") is not None else None),
        assignee_team=(str(body.get("assignee_team")) if body.get("assignee_team") else None),
        stage=(str(body.get("stage")) if body.get("stage") is not None else None),
        sla_hours=(int(body.get("sla_hours")) if body.get("sla_hours") is not None else None),
        related_alert=(str(body.get("related_alert")) if body.get("related_alert") else None),
        object_type=(str(body.get("object_type")) if body.get("object_type") else None),
        object_id=(str(body.get("object_id")) if body.get("object_id") else None),
        attachments=list(body.get("attachments") or []),
        why=dict(body.get("why") or {}),
        what_to_do=list(body.get("what_to_do") or []),
        data_version=(str(body.get("data_version")) if body.get("data_version") else None),
        qc_run=(str(body.get("qc_run")) if body.get("qc_run") else None),
        model_version=(str(body.get("model_version")) if body.get("model_version") else None),
        scoring_run=(str(body.get("scoring_run")) if body.get("scoring_run") else None),
        report_version=(str(body.get("report_version")) if body.get("report_version") else None),
        dedupe_key=(str(body.get("dedupe_key")) if body.get("dedupe_key") else None),
    )
    try:
        task_id = create_task(conn, tenant_id=tenant_id, t=t)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)[:500]})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.create",
        object_type="task_v1",
        object_id=task_id,
        data_version=t.data_version,
        after={
            "task_type": t.task_type,
            "domain": t.domain,
            "priority": t.priority,
            "assignee_team": t.assignee_team,
            "related_alert": t.related_alert,
            "object": [t.object_type, t.object_id],
        },
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"task_id": task_id}


@app.post("/api/tasks_v1/generate_from_alerts")
def api_tasks_v1_generate_from_alerts(
    data_version: Optional[str] = None,
    user=Depends(require_permissions("tasks.generate")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    catalog = load_tasks_catalog(settings.project_root / "configs" / "tasks_v1" / "catalog.yaml")
    res = upsert_tasks_from_alerts(conn, tenant_id=tenant_id, catalog=catalog, data_version=data_version)
    return {"ok": True, **res}


@app.post("/api/tasks_v1/{task_id}/take")
def api_tasks_v1_take(
    task_id: str,
    request: Request,
    user=Depends(require_permissions("tasks.close")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    res = take_task_use_case(conn=conn, tenant_id=tenant_id, task_id=task_id, user_id=int(user.get("id", 0)))
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.take",
        object_type="task_v1",
        object_id=task_id,
        status="OK",
        ip=ip,
        user_agent=ua,
    )
    return {"ok": True}


@app.post("/api/tasks_v1/{task_id}/assign")
async def api_tasks_v1_assign(
    task_id: str,
    request: Request,
    user=Depends(require_permissions("tasks.write")),
    conn=Depends(get_db),
):
    body = await request.json()
    owner_user_id = body.get("owner_user_id")
    assignee_username = body.get("assignee_username")
    assignee_team = body.get("assignee_team")
    tenant_id = user.get("tenant_id", "default")
    # Username-based assignment convenience
    if owner_user_id is None and (assignee_username or "").strip():
        u = get_user_by_username(conn, username=str(assignee_username).strip(), tenant_id=tenant_id)
        if not u:
            raise HTTPException(status_code=400, detail={"error": "invalid_assignee_username", "hint": str(assignee_username)})
        owner_user_id = int(u.get("id"))

    if owner_user_id is None and not (assignee_team or "").strip():
        raise HTTPException(status_code=400, detail={"error": "assignee_required", "hint": "owner_user_id or assignee_team"})
    
    before = None
    try:
        before = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    except Exception:
        before = None
    try:
        assign_task(
            conn,
            tenant_id=tenant_id,
            task_id=task_id,
            owner_user_id=(int(owner_user_id) if owner_user_id is not None else None),
            assignee_team=(str(assignee_team).strip() if assignee_team else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(status_code=404)

    ip, ua = _get_ip_ua(request)
    after = None
    try:
        after = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    except Exception:
        after = None
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.assign",
        object_type="task_v1",
        object_id=task_id,
        before=(before or {}),
        after=(after or {"owner_user_id": owner_user_id, "assignee_team": assignee_team}),
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


@app.post("/api/tasks_v1/{task_id}/update")
async def api_tasks_v1_update(
    task_id: str,
    request: Request,
    user=Depends(require_permissions("tasks.write")),
    conn=Depends(get_db),
):
    """Update editable fields: priority/domain/due/status(open|in_progress)/assignee."""

    tenant_id = user.get("tenant_id", "default")
    body = await request.json()

    # Convenience: set assignee by username
    if isinstance(body, dict) and (body.get("assignee_username") or "").strip():
        u = get_user_by_username(conn, username=str(body.get("assignee_username")).strip(), tenant_id=tenant_id)
        if not u:
            raise HTTPException(status_code=400, detail={"error": "invalid_assignee_username", "hint": str(body.get("assignee_username"))})
        body = dict(body)
        body["owner_user_id"] = int(u.get("id"))
        body.pop("assignee_username", None)

    before = None
    try:
        before = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    except Exception:
        before = None

    try:
        res = update_task_use_case(conn=conn, tenant_id=tenant_id, task_id=task_id, patch=dict(body or {}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(status_code=404)

    after = res.get("after") or None

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.update",
        object_type="task_v1",
        object_id=task_id,
        data_version=(after or {}).get("data_version") if after else None,
        before=(before or {}),
        after=(after or {}),
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    return {"ok": True}


@app.post("/api/tasks_v1/{task_id}/close")
async def api_tasks_v1_close(
    task_id: str,
    request: Request,
    user=Depends(require_permissions("tasks.close")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    status = str(body.get("status") or "").strip()
    reason = str(body.get("reason") or "").strip()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    if not status or not reason:
        raise HTTPException(status_code=400, detail={"error": "status_and_reason_required"})

    try:
        res = close_task_use_case(
            conn=conn,
            tenant_id=tenant_id,
            task_id=task_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            status=status,
            reason=reason,
            comment=comment,
            resolve_related_alert=bool(body.get("resolve_related_alert", True)),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(status_code=404)

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="tasks_v1.close",
        object_type="task_v1",
        object_id=task_id,
        after={"status": res.get("status") or status, "reason": res.get("reason") or reason},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


# --- T12-03: Playbooks (checklists for alerts/tasks) ---


@app.get("/api/playbooks_v1")
def api_playbooks_v1_list(
    target_kind: str | None = None,
    target_type: str | None = None,
    farm_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions("playbooks.view")),
    conn=Depends(get_db),
):
    from .playbooks_v1 import list_versions

    tenant_id = user.get("tenant_id", "default")
    try:
        versions = list_versions(
            conn,
            tenant_id=tenant_id,
            target_kind=target_kind,
            target_type=target_type,
            farm_id=farm_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    return {"versions": versions}


@app.get("/api/playbooks_v1/active")
def api_playbooks_v1_active(
    target_kind: str,
    target_type: str,
    farm_id: str | None = None,
    user=Depends(require_permissions("playbooks.view")),
    conn=Depends(get_db),
):
    from .playbooks_v1 import get_active_playbook

    tenant_id = user.get("tenant_id", "default")
    try:
        pb = get_active_playbook(conn, tenant_id=tenant_id, target_kind=target_kind, target_type=target_type, farm_id=farm_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    return {"playbook": pb}


@app.post("/api/playbooks_v1")
async def api_playbooks_v1_create(
    request: Request,
    user=Depends(require_permissions("playbooks.write")),
    conn=Depends(get_db),
):
    from .playbooks_v1 import PlaybookCreate, create_playbook_version, get_active_version_state, make_playbook_key

    tenant_id = user.get("tenant_id", "default")
    body = await request.json()

    pb = PlaybookCreate(
        target_kind=str(body.get("target_kind") or ""),
        target_type=str(body.get("target_type") or ""),
        farm_id=str(body.get("farm_id") or ""),
        name=str(body.get("name") or ""),
        description=str(body.get("description") or ""),
        steps=list(body.get("steps") or []),
        comment=str(body.get("comment") or ""),
        set_active=bool(body.get("set_active", True)),
    )

    playbook_key = None
    before_active = None
    try:
        playbook_key = make_playbook_key(target_kind=pb.target_kind, target_type=pb.target_type)
        before_active = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=pb.farm_id or "")

        vid = create_playbook_version(
            conn,
            tenant_id=tenant_id,
            pb=pb,
            created_by=int(user.get("id", 0)) or None,
            created_by_username=str(user.get("username", "")) or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    # audit
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="playbooks_v1.create_version",
        object_type="playbook",
        object_id=str(vid),
        before={"active": before_active, "playbook_key": playbook_key},
        after={
            "playbook_key": playbook_key,
            "target_kind": pb.target_kind,
            "target_type": pb.target_type,
            "farm_id": pb.farm_id,
            "name": pb.name,
            "set_active": bool(pb.set_active),
        },
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "version_id": vid, "playbook_key": playbook_key}


@app.post("/api/playbooks_v1/{version_id}/activate")
async def api_playbooks_v1_activate(
    version_id: str,
    request: Request,
    user=Depends(require_permissions("playbooks.write")),
    conn=Depends(get_db),
):
    from .playbooks_v1 import get_active_version_state, set_active_playbook

    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    playbook_key = str(body.get("playbook_key") or "").strip()
    farm_id = str(body.get("farm_id") or "").strip()
    if not playbook_key:
        raise HTTPException(status_code=400, detail={"error": "playbook_key_required"})

    before = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id)

    try:
        set_active_playbook(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id, version_id=version_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(status_code=404)

    after = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id)

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="playbooks_v1.activate",
        object_type="playbook",
        object_id=str(version_id),
        before={"active": before, "playbook_key": playbook_key, "farm_id": farm_id},
        after={"active": after, "playbook_key": playbook_key, "farm_id": farm_id},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


# --- What-If 2.0: saved scenarios (T11-04) ---


@app.get("/api/whatif_scenarios_v1")
def api_whatif_scenarios_list(
    status: Optional[str] = None,
    q: Optional[str] = None,
    include_playbook: bool = False,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    return list_scenarios(conn, tenant_id=tenant_id, status=status, q=q, limit=int(limit), offset=int(offset))


@app.get("/api/whatif_scenarios_v1/{scenario_id}")
def api_whatif_scenario_get(
    scenario_id: str,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    s = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not s:
        raise HTTPException(404)
    return s


@app.post("/api/whatif_scenarios_v1")
async def api_whatif_scenario_create(
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail={"error": "name_required"})
    s = WhatIfScenarioCreate(
        name=name,
        description=(str(body.get("description")) if body.get("description") else None),
        data_version=(str(body.get("data_version")) if body.get("data_version") else None),
        params=(dict(body.get("params") or {})),
    )
    try:
        scenario_id = create_scenario(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            s=s,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.create",
        object_type="whatif_scenario",
        object_id=scenario_id,
        data_version=s.data_version,
        after={"name": s.name, "status": "draft"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"scenario_id": scenario_id}


@app.post("/api/whatif_scenarios_v1/{scenario_id}/update")
async def api_whatif_scenario_update(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    try:
        update_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            name=(str(body.get("name")) if body.get("name") is not None else None),
            description=(str(body.get("description")) if body.get("description") is not None else None),
            data_version=(str(body.get("data_version")) if body.get("data_version") is not None else None),
            params=(dict(body.get("params")) if body.get("params") is not None else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.update",
        object_type="whatif_scenario",
        object_id=scenario_id,
        data_version=(after or {}).get("data_version"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


@app.post("/api/whatif_scenarios_v1/{scenario_id}/approve")
async def api_whatif_scenario_approve(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    try:
        approve_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            approved_by=int(user.get("id", 0)),
            approved_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.approve",
        object_type="whatif_scenario",
        object_id=scenario_id,
        data_version=(after or {}).get("data_version"),
        run_id=_scenario_run_id(after),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )


@app.post("/api/whatif_scenarios_v1/{scenario_id}/reject")
async def api_whatif_scenario_reject(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_APPROVE)),
    conn=Depends(get_db),
):
    """Director rejects scenario with a comment (keeps status='draft')."""

    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    try:
        reject_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            rejected_by=int(user.get("id", 0)),
            rejected_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.reject",
        object_type="whatif_scenario",
        object_id=scenario_id,
        data_version=(after or {}).get("data_version"),
        run_id=_scenario_run_id(after),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}
    return {"ok": True}


@app.post("/api/whatif_scenarios_v1/{scenario_id}/clone")
async def api_whatif_scenario_clone(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_CLONE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)

    body = await request.json()
    new_name = (str(body.get("name")).strip() if body.get("name") is not None else None)
    new_desc = (str(body.get("description")).strip() if body.get("description") is not None else None)

    try:
        new_id = clone_scenario(
            conn,
            tenant_id=tenant_id,
            source_scenario_id=scenario_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            name=new_name,
            description=new_desc,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=new_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.clone",
        object_type="whatif_scenario",
        object_id=str(new_id),
        data_version=(after or {}).get("data_version"),
        run_id=_scenario_run_id(after),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"scenario_id": new_id}


@app.post("/api/whatif_scenarios_v1/{scenario_id}/archive")
async def api_whatif_scenario_archive(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_ARCHIVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)

    try:
        archive_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            archived_by=int(user.get("id", 0)),
            archived_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.archive",
        object_type="whatif_scenario",
        object_id=str(scenario_id),
        data_version=(after or {}).get("data_version"),
        run_id=_scenario_run_id(after),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


# --- T12-04: Weekly Plans approvals (draft -> approved -> archived) ---


@app.get("/api/weekly_plans_v1")
def api_weekly_plans_list(
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    return list_weekly_plans(conn, tenant_id=tenant_id, status=status, q=q, limit=int(limit), offset=int(offset))


@app.get("/api/weekly_plans_v1/pending_approval")
def api_weekly_plans_pending_approval(
    limit: int = 100,
    offset: int = 0,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    res = list_pending_approval_weekly_plans(conn, tenant_id=tenant_id, limit=int(limit), offset=int(offset))
    return {
        "total": int(res.get("total") or 0),
        "weekly_plans": [summarize_weekly_plan(p) for p in list(res.get("weekly_plans") or [])],
    }


@app.post("/api/weekly_plans_v1/generate")
async def api_weekly_plan_generate(
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    week_start = str(body.get("week_start") or "").strip()
    data_version = str(body.get("data_version") or "").strip()
    question = str(body.get("question") or "Сформируй план на неделю").strip()
    farm_id = (str(body.get("farm_id")).strip() if body.get("farm_id") else None)
    if not data_version or not week_start:
        raise HTTPException(status_code=400, detail={"error": "data_version_and_week_start_required"})
    try:
        plan = _generate_weekly_plan_payload(
            data_version=data_version,
            week_start=week_start,
            question=question,
            farm_id=farm_id,
        )
        plan_id = create_weekly_plan(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            p=WeeklyPlanCreate(
                name=str(plan.get("name") or f"AI-план на неделю {week_start}"),
                week_start=str(plan.get("week_start") or week_start),
                summary=str(plan.get("summary") or ""),
                farm_id=(str(plan.get("farm_id")) if plan.get("farm_id") else None),
                data_version=str(plan.get("data_version") or data_version),
                action_items=list(plan.get("action_items") or []),
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.generate",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        run_id=_best_run_id((list(plan.get("source_run_ids") or [None])[0])),
        after={
            "plan": after,
            "generator": plan.get("generator"),
            "question": plan.get("question"),
            "source_run_ids": list(plan.get("source_run_ids") or []),
            "source_sections": list(plan.get("source_sections") or []),
            "item_count": len(list(plan.get("action_items") or [])),
            "via": "api",
        },
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"plan_id": plan_id, "plan": after, "generated_plan": plan}


@app.get("/api/weekly_plans_v1/{plan_id}")
def api_weekly_plan_get(
    plan_id: str,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    p = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not p:
        raise HTTPException(404)
    return p


@app.post("/api/weekly_plans_v1")
async def api_weekly_plan_create(
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    body = await request.json()
    name = str(body.get("name") or "").strip()
    week_start = str(body.get("week_start") or "").strip()
    if not name or not week_start:
        raise HTTPException(status_code=400, detail={"error": "name_and_week_start_required"})
    p = WeeklyPlanCreate(
        name=name,
        week_start=week_start,
        summary=(str(body.get("summary")) if body.get("summary") else None),
        farm_id=(str(body.get("farm_id")) if body.get("farm_id") else None),
        data_version=(str(body.get("data_version")) if body.get("data_version") else None),
        action_items=(list(body.get("action_items") or []) if isinstance(body.get("action_items"), list) else None),
    )
    try:
        plan_id = create_weekly_plan(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            p=p,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.create",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"plan_id": plan_id}


@app.post("/api/weekly_plans_v1/{plan_id}/update")
async def api_weekly_plan_update(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    try:
        update_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            name=(str(body.get("name")) if body.get("name") is not None else None),
            summary=(str(body.get("summary")) if body.get("summary") is not None else None),
            farm_id=(str(body.get("farm_id")) if body.get("farm_id") is not None else None),
            data_version=(str(body.get("data_version")) if body.get("data_version") is not None else None),
            week_start=(str(body.get("week_start")) if body.get("week_start") is not None else None),
            action_items=(list(body.get("action_items")) if body.get("action_items") is not None else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.update",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


@app.post("/api/weekly_plans_v1/{plan_id}/request_approval")
async def api_weekly_plan_request_approval(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    try:
        res = request_approval_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            requested_by=int(user.get("id", 0)),
            requested_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.request_approval",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"plan": after, "request": res, "via": "api"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "plan": after, "request": res}


@app.post("/api/weekly_plans_v1/{plan_id}/export_pdf")
async def api_weekly_plan_export_pdf(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        rep = export_weekly_plan_pdf(
            conn,
            artifacts_root=settings.artifacts_root,
            tenant_id=tenant_id,
            plan_id=plan_id,
            exported_by=int(user.get("id", 0)),
            exported_by_username=str(user.get("username", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.export_pdf",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"plan": after, "pdf_rel_path": rep.get("pdf_rel_path"), "meta_path": rep.get("meta_path"), "via": "api"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, **rep}


@app.post("/api/weekly_plans_v1/{plan_id}/approve")
async def api_weekly_plan_approve(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    try:
        res = approve_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            approved_by=int(user.get("id", 0)),
            approved_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.approve",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        run_id=_best_run_id((res or {}).get("tasks_run_id")),
        before=before,
        after={"plan": after, "tasks": {"created": (res.get("tasks_created") or [])[:20], "reused": (res.get("tasks_reused") or [])[:20], "tasks_run_id": res.get("tasks_run_id")}},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "tasks": res}


@app.post("/api/weekly_plans_v1/{plan_id}/reject")
async def api_weekly_plan_reject(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    try:
        reject_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            rejected_by=int(user.get("id", 0)),
            rejected_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.reject",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


@app.post("/api/weekly_plans_v1/{plan_id}/archive")
async def api_weekly_plan_archive(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_ARCHIVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    body = await request.json()
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)
    try:
        archive_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            archived_by=int(user.get("id", 0)),
            archived_by_username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.archive",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True}


# --- T12-04: Approvals for regular reports (draft -> approved -> archived) ---


@app.get("/api/reports_v1/approval")
def api_report_approval_get(
    data_version: str,
    report_version: str,
    user=Depends(require_permissions(rbac.PERM_REPORTS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    row = get_report_approval(conn, tenant_id=tenant_id, data_version=data_version, report_version=report_version)
    return {"data_version": data_version, "report_version": report_version, "approval": row or {"status": "draft"}}


@app.post("/api/reports_v1/{report_version}/approve")
async def api_report_approve(
    report_version: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_REPORTS_APPROVE)),
    conn=Depends(get_db),
):
    body = await request.json()
    dv = (str(body.get("data_version")) if body.get("data_version") else "").strip()
    if not dv:
        raise HTTPException(status_code=400, detail={"error": "reports.data_version пуст"})

    # validate report exists in artifacts
    rep_dir = settings.artifacts_root / dv / "reports" / report_version
    if not rep_dir.exists():
        raise HTTPException(status_code=404, detail={"error": f"report_not_found: {dv}/{report_version}"})
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)

    tenant_id = user.get("tenant_id", "default")
    before = get_report_approval(conn, tenant_id=tenant_id, data_version=dv, report_version=report_version)
    try:
        changed = approve_report(
            conn,
            tenant_id=tenant_id,
            data_version=dv,
            report_version=report_version,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="report.approve",
        object_type="report",
        object_id=f"{dv}:{report_version}",
        data_version=dv,
        run_id=report_version,
        before=before,
        after=changed.get("after"),
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "approval": changed.get("after")}


@app.post("/api/reports_v1/{report_version}/reject")
async def api_report_reject(
    report_version: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_REPORTS_APPROVE)),
    conn=Depends(get_db),
):
    body = await request.json()
    dv = (str(body.get("data_version")) if body.get("data_version") else "").strip()
    if not dv:
        raise HTTPException(status_code=400, detail={"error": "reports.data_version пуст"})

    rep_dir = settings.artifacts_root / dv / "reports" / report_version
    if not rep_dir.exists():
        raise HTTPException(status_code=404, detail={"error": f"report_not_found: {dv}/{report_version}"})
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)

    tenant_id = user.get("tenant_id", "default")
    before = get_report_approval(conn, tenant_id=tenant_id, data_version=dv, report_version=report_version)
    try:
        changed = reject_report(
            conn,
            tenant_id=tenant_id,
            data_version=dv,
            report_version=report_version,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="report.reject",
        object_type="report",
        object_id=f"{dv}:{report_version}",
        data_version=dv,
        run_id=report_version,
        before=before,
        after=changed.get("after"),
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "approval": changed.get("after")}


@app.post("/api/reports_v1/{report_version}/archive")
async def api_report_archive(
    report_version: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_REPORTS_ARCHIVE)),
    conn=Depends(get_db),
):
    body = await request.json()
    dv = (str(body.get("data_version")) if body.get("data_version") else "").strip()
    if not dv:
        raise HTTPException(status_code=400, detail={"error": "reports.data_version пуст"})

    rep_dir = settings.artifacts_root / dv / "reports" / report_version
    if not rep_dir.exists():
        raise HTTPException(status_code=404, detail={"error": f"report_not_found: {dv}/{report_version}"})
    comment = (str(body.get("comment")).strip() if body.get("comment") else None)

    tenant_id = user.get("tenant_id", "default")
    before = get_report_approval(conn, tenant_id=tenant_id, data_version=dv, report_version=report_version)
    try:
        changed = archive_report(
            conn,
            tenant_id=tenant_id,
            data_version=dv,
            report_version=report_version,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="report.archive",
        object_type="report",
        object_id=f"{dv}:{report_version}",
        data_version=dv,
        run_id=report_version,
        before=before,
        after=changed.get("after"),
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return {"ok": True, "approval": changed.get("after")}


@app.post("/api/whatif_compare_v1")
async def api_whatif_compare_v1(
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_VIEW)),
    conn=Depends(get_db),
):
    """Compare 2–3 saved what-if scenarios against BASE.

    Runs economics in offline-core and returns an aggregated comparison table + run IDs.
    """

    tenant_id = user.get("tenant_id", "default")
    _require_or_403(user, rbac.PERM_PIPELINE_RUN)

    body = await request.json()
    scenario_ids = list(body.get("scenario_ids") or [])
    if not isinstance(scenario_ids, list):
        raise HTTPException(status_code=400, detail={"error": "scenario_ids_must_be_list"})
    scenario_ids = [str(x) for x in scenario_ids if str(x).strip()]
    if len(scenario_ids) < 2:
        raise HTTPException(status_code=400, detail={"error": "need_2_or_3_scenarios"})
    if len(scenario_ids) > 3:
        raise HTTPException(status_code=400, detail={"error": "max_3_scenarios"})

    base_ctx = dict(body.get("base_context") or {})

    loaded = []
    for sid in scenario_ids:
        row = get_scenario(conn, tenant_id=tenant_id, scenario_id=sid)
        if not row:
            raise HTTPException(status_code=404, detail={"error": "scenario_not_found", "scenario_id": sid})
        if str(row.get("status") or "") == "archived":
            raise HTTPException(status_code=400, detail={"error": "scenario_archived", "scenario_id": sid})
        loaded.append(row)

    first = loaded[0]
    first_params = dict((first.get("params") or {}) if isinstance(first.get("params"), dict) else {})
    data_version = str(base_ctx.get("data_version") or first.get("data_version") or "")
    date_from = str(base_ctx.get("date_from") or first_params.get("date_from") or "")
    date_to = str(base_ctx.get("date_to") or first_params.get("date_to") or "")
    cfg_path = str(base_ctx.get("cfg_path") or first_params.get("cfg_path") or "configs/economics/economics_v1.yaml")

    if not data_version or not date_from or not date_to:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "base_context_required",
                "message": "data_version/date_from/date_to обязательны",
            },
        )

    mismatches = []
    scenarios_rows = []
    for row in loaded:
        sid = str(row.get("scenario_id") or "")
        params = dict((row.get("params") or {}) if isinstance(row.get("params"), dict) else {})
        dv = str(row.get("data_version") or data_version)
        df0 = str(params.get("date_from") or date_from)
        df1 = str(params.get("date_to") or date_to)
        cfgp = str(params.get("cfg_path") or cfg_path)
        if dv != data_version:
            mismatches.append(f"{sid[:8]}: data_version={dv} (ожидается {data_version})")
        if df0 != date_from:
            mismatches.append(f"{sid[:8]}: date_from={df0} (ожидается {date_from})")
        if df1 != date_to:
            mismatches.append(f"{sid[:8]}: date_to={df1} (ожидается {date_to})")
        if cfgp != cfg_path:
            mismatches.append(f"{sid[:8]}: cfg_path={cfgp} (ожидается {cfg_path})")

        name = (str(row.get("name") or "scenario").strip() or "scenario")
        uniq_name = f"{name} — {sid[:8]}"
        scenarios_rows.append(
            {
                "scenario_id": sid,
                "name": uniq_name,
                "milk_price_multiplier": float(params.get("milk_price_multiplier") or 1.0),
                "feed_cost_multiplier": float(params.get("feed_cost_multiplier") or 1.0),
                "other_cost_multiplier": float(params.get("other_cost_multiplier") or 1.0),
            }
        )

    if mismatches:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "context_mismatch",
                "message": "Сценарии должны иметь одинаковые data_version/date_from/date_to/cfg_path",
                "mismatches": mismatches,
            },
        )

    from genomeai.economics_whatif import compare_whatif_scenarios

    try:
        res = compare_whatif_scenarios(
            artifacts_root=settings.artifacts_root,
            data_version=data_version,
            date_from=date_from,
            date_to=date_to,
            cfg_path=Path(cfg_path),
            scenarios=[
                {
                    "name": s["name"],
                    "milk_price_multiplier": s["milk_price_multiplier"],
                    "feed_cost_multiplier": s["feed_cost_multiplier"],
                    "other_cost_multiplier": s["other_cost_multiplier"],
                }
                for s in scenarios_rows
            ],
            tenant_id=tenant_id,
        )
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="whatif_scenario.compare",
            object_type="whatif_compare",
            object_id=",".join(scenario_ids),
            data_version=data_version,
            status="ERROR",
            error=str(e),
            ip=ip,
            user_agent=ua,
        )
        raise HTTPException(status_code=500, detail={"error": "compare_failed", "detail": str(e)})

    scenario_runs_by_name = dict(res.get("scenario_runs") or {})
    scenario_runs_by_id: dict[str, str] = {}
    for s in scenarios_rows:
        sid = str(s["scenario_id"])
        rid = str(scenario_runs_by_name.get(str(s["name"]) or "") or "")
        if rid:
            scenario_runs_by_id[sid] = rid
            try:
                attach_last_run(conn, tenant_id=tenant_id, scenario_id=sid, economics_run=rid)
            except Exception:
                pass
            try:
                ip, ua = _get_ip_ua(request)
                write_audit(
                    conn,
                    tenant_id=tenant_id,
                    user_id=int(user.get("id", 0)),
                    username=user.get("username", ""),
                    role=user.get("role", ""),
                    action="whatif_scenario.run",
                    object_type="whatif_scenario",
                    object_id=sid,
                    data_version=data_version,
                    run_id=rid,
                    after={"economics_run": rid, "source": "compare"},
                    ip=ip,
                    user_agent=ua,
                    status="OK",
                )
            except Exception:
                pass

    base_run = str(res.get("base_economics_run") or "")
    xlsx_base = (
        str(Path("artifacts") / data_version / "economics" / base_run / "economics_whatif.xlsx")
        if base_run
        else None
    )
    xlsx_by_scenario = {
        sid: str(Path("artifacts") / data_version / "economics" / rid / "economics_whatif.xlsx")
        for sid, rid in scenario_runs_by_id.items()
    }

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.compare",
        object_type="whatif_compare",
        object_id=",".join(scenario_ids),
        data_version=data_version,
        after={"base_run": base_run, "scenario_runs": scenario_runs_by_id},
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    return {
        "ok": True,
        "data_version": data_version,
        "date_from": date_from,
        "date_to": date_to,
        "cfg_path": cfg_path,
        "base_economics_run": base_run,
        "scenario_runs": scenario_runs_by_id,
        "comparison": res.get("comparison") or [],
        "xlsx_base": xlsx_base,
        "xlsx_by_scenario": xlsx_by_scenario,
    }


# --- What-If 2.0: scenario PDF reports (T11-04) ---


@app.get("/api/whatif_reports_v1")
def api_whatif_reports_list(
    scenario_id: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_permissions(rbac.PERM_WHATIF_REPORT_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    return list_whatif_reports(conn, tenant_id=tenant_id, scenario_id=scenario_id, limit=int(limit), offset=int(offset))


@app.get("/api/whatif_reports_v1/{report_version}")
def api_whatif_report_get(
    report_version: str,
    user=Depends(require_permissions(rbac.PERM_WHATIF_REPORT_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    r = get_whatif_report(conn, tenant_id=tenant_id, report_version=report_version)
    if not r:
        raise HTTPException(404)
    return r


@app.post("/api/whatif_scenarios_v1/{scenario_id}/report_pdf")
async def api_whatif_report_generate(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_REPORT_GENERATE)),
    conn=Depends(get_db),
):
    """Generate a fact-based PDF report for a saved what-if scenario."""

    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)

    body = await request.json()
    reuse_last_run = bool(body.get("reuse_last_run", True))

    params = dict((before.get("params") or {}) if isinstance(before.get("params"), dict) else {})
    data_version = str(before.get("data_version") or params.get("data_version") or "")
    if not data_version:
        raise HTTPException(status_code=400, detail={"error": "data_version_required"})

    date_from = str(params.get("date_from") or "")
    date_to = str(params.get("date_to") or "")
    cfg_path = str(params.get("cfg_path") or "configs/economics/economics_v1.yaml")

    # Governance: optional approval requirement
    if str(before.get("status") or "") == "archived":
        raise HTTPException(status_code=400, detail={"error": "scenario_archived", "message": "Сценарий архивирован"})
    if _get_governance_flag(cfg_path, "require_approval_for_report_pdf", default=False):
        if str(before.get("status") or "") != "approved":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "scenario_not_approved",
                    "message": "Для генерации PDF требуется утверждение сценария",
                    "scenario_status": str(before.get("status") or ""),
                },
            )

    milk_mult = float(params.get("milk_price_multiplier") or 1.0)
    feed_mult = float(params.get("feed_cost_multiplier") or 1.0)
    other_mult = float(params.get("other_cost_multiplier") or 1.0)

    # Determine economics runs
    scenario_run = str(before.get("last_economics_run") or "") if reuse_last_run else ""

    from genomeai.economics_whatif import run_economics_whatif

    if not scenario_run:
        # Need pipeline.run to compute
        _require_or_403(user, rbac.PERM_PIPELINE_RUN)
        res = run_economics_whatif(
            artifacts_root=settings.artifacts_root,
            data_version=data_version,
            date_from=date_from,
            date_to=date_to,
            milk_price_multiplier=milk_mult,
            feed_cost_multiplier=feed_mult,
            other_cost_multiplier=other_mult,
            cfg_path=Path(cfg_path),
            tenant_id=tenant_id,
        )
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail={"error": "economics_run_failed", "reason": res.get("reason")})
        scenario_run = str(res.get("economics_run") or "")

    # Persist last run on scenario for future reuse (RBAC: director can generate report without pipeline.run)
    try:
        attach_last_run(conn, tenant_id=tenant_id, scenario_id=scenario_id, economics_run=scenario_run)
    except Exception:
        pass

    # Best-effort audit: scenario run
    try:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="whatif_scenario.run",
            object_type="whatif_scenario",
            object_id=str(scenario_id),
            data_version=data_version,
            run_id=str(scenario_run),
            after={"economics_run": scenario_run},
            ip=ip,
            user_agent=ua,
            status="OK",
        )
    except Exception:
        pass

    # BASE vs SCENARIO are both stored inside the same economics_run directory.
    # Therefore, for the report we can reuse the same run id for baseline and scenario.
    base_run = scenario_run

    from genomeai.whatif_report import generate_whatif_report_pdf

    try:
        rep = generate_whatif_report_pdf(
            artifacts_root=settings.artifacts_root,
            data_version=data_version,
            scenario_id=str(before.get("scenario_id") or scenario_id),
            scenario_name=str(before.get("name") or "Scenario"),
            scenario_params={
                "milk_price_multiplier": milk_mult,
                "feed_cost_multiplier": feed_mult,
                "other_cost_multiplier": other_mult,
            },
            scenario_meta={
                "status": before.get("status"),
                "created_by_username": before.get("created_by_username"),
                "approved_at": before.get("approved_at"),
                "approved_by_username": before.get("approved_by_username"),
                "approval_comment": before.get("approval_comment"),
                "archived_at": before.get("archived_at"),
                "archived_by_username": before.get("archived_by_username"),
                "archive_comment": before.get("archive_comment"),
                "cloned_from_scenario_id": before.get("cloned_from_scenario_id"),
            },
            date_from=date_from,
            date_to=date_to,
            cfg_path=cfg_path,
            base_economics_run=base_run,
            scenario_economics_run=scenario_run,
        )
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="whatif_report.generate",
            object_type="whatif_scenario",
            object_id=scenario_id,
            data_version=data_version,
            status="ERROR",
            error=str(e),
            ip=ip,
            user_agent=ua,
        )
        raise HTTPException(status_code=500, detail={"error": "report_failed", "detail": str(e)})

    # Store artifacts-relative path for /download
    rel_pdf = str(Path("artifacts") / data_version / "whatif_reports" / rep["report_version"] / "whatif_report.pdf")

    create_report(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=str(user.get("username", "")),
        r=WhatIfReportCreate(
            scenario_id=str(before.get("scenario_id") or scenario_id),
            report_version=str(rep.get("report_version")),
            data_version=data_version,
            base_economics_run=base_run,
            scenario_economics_run=scenario_run,
            pdf_rel_path=rel_pdf,
            params={
                "date_from": date_from,
                "date_to": date_to,
                "cfg_path": cfg_path,
                "milk_price_multiplier": milk_mult,
                "feed_cost_multiplier": feed_mult,
                "other_cost_multiplier": other_mult,
            },
        ),
    )

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_report.generate",
        object_type="whatif_report",
        object_id=str(rep.get("report_version")),
        data_version=data_version,
        after={"scenario_id": scenario_id, "report_version": rep.get("report_version"), "pdf": rel_pdf},
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    return {"ok": True, "report_version": rep.get("report_version"), "pdf_rel_path": rel_pdf}


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(
    request: Request,
    status: Optional[str] = None,
    pipeline: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    auto_refresh: int = 0,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    jobs = list_jobs_filtered(conn, status=status, pipeline=pipeline, q=q, limit=limit)
    jobs_payload = [_serialize_job_row(r) for r in jobs]
    has_active = any(str(j.get("status") or "") in ACTIVE_JOB_STATUSES for j in jobs_payload)
    return _render(
        request,
        "tasks.html",
        user=user,
        jobs=jobs_payload,
        filters={"status": status or "", "pipeline": pipeline or "", "q": q or "", "limit": int(limit or 200), "auto_refresh": int(auto_refresh or 0)},
        active="jobs",
        auto_refresh_enabled=bool(auto_refresh),
        auto_refresh_sec=int(job_runner_cfg.ui_auto_refresh_sec),
        has_active_jobs=has_active,
    )


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    return jobs_page(request, user=user, conn=conn)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: int, request: Request, auto_refresh: int = 1, user=Depends(get_current_user), conn=Depends(get_db)):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404)
    job = _serialize_job_row(row)
    family = _job_family_rows(conn, job_id)
    return _render(
        request,
        "job.html",
        user=user,
        job=job,
        family=family,
        log_text=_job_log_text(job),
        active="jobs",
        auto_refresh_enabled=bool(auto_refresh),
        auto_refresh_sec=int(job_runner_cfg.ui_auto_refresh_sec),
        is_active_job=str(job.get("status") or "") in ACTIVE_JOB_STATUSES,
        log_stream_chunk_bytes=int(job_runner_cfg.log_stream_chunk_bytes),
    )


@app.get("/tasks/{job_id}", response_class=HTMLResponse)
def job_page_legacy(job_id: int, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    return job_page(job_id, request, user=user, conn=conn)


@app.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
def job_log(job_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    row = RunsRepo(conn).get_job(job_id)
    if not row:
        raise HTTPException(404)
    job = dict(row)
    try:
        text = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir).read_text(Path(job["log_path"]))
    except Exception:
        text = ""
    return PlainTextResponse(text)


@app.get("/tasks/{job_id}/log", response_class=PlainTextResponse)
def job_log_legacy(job_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    return job_log(job_id, user=user, conn=conn)


@app.get("/download")
def download(request: Request, path: str, user=Depends(require_permissions("export.download")), conn=Depends(get_db)):
    """Download files from allowed roots (artifacts/web storage/project)."""
    # Viewer is allowed.
    rel = (path or '').lstrip('/')
    # Virtual roots to avoid leaking absolute paths in templates.
    root_map = {
        'artifacts': settings.artifacts_root,
        'web_storage': settings.storage_dir,
        'project': settings.project_root,
    }
    base = settings.project_root
    rel2 = rel
    for prefix, b in root_map.items():
        if rel == prefix or rel.startswith(prefix + '/'):
            base = b
            rel2 = rel[len(prefix):].lstrip('/')
            break
    if not rel2:
        raise HTTPException(400, 'empty path')
    try:
        p = safe_join(base, rel2)
    except ValueError:
        raise HTTPException(400, 'unsafe path')
    if not p.exists() or not p.is_file():
        raise HTTPException(404)
    write_audit(conn, tenant_id=user.get("tenant_id","default"), user_id=int(user.get("id",0)), username=user.get("username",""), role=user.get("role",""), action="export.download", object_type="file", object_id=rel, after={"filename": p.name, "size": p.stat().st_size}, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), status="OK")
    return FileResponse(str(p), filename=p.name)

@app.get("/connectors", response_class=HTMLResponse)
def connectors_page(request: Request, user=Depends(require_permissions("pipeline.run")), conn=Depends(get_db)):
    configs_dir = _connector_configs_dir()
    catalog = catalog_with_state(conn, tenant_id=user["tenant_id"], configs_dir=configs_dir)
    runs = list_connector_runs(conn, tenant_id=user["tenant_id"], limit=100)
    notice = request.query_params.get("notice") or ""
    error = request.query_params.get("error") or ""
    catalog_summary = summarize_catalog_health(catalog, now=datetime.now(timezone.utc))
    return _render(
        request,
        "connectors.html",
        user=user,
        active="connectors",
        catalog=catalog,
        runs=runs,
        configs_dir=str(configs_dir),
        notice=notice,
        error=error,
        catalog_summary=catalog_summary,
    )


@app.get("/connectors/new", response_class=HTMLResponse)
def connector_new_page(request: Request, user=Depends(require_permissions("pipeline.run"))):
    notice = request.query_params.get("notice") or ""
    error = request.query_params.get("error") or ""
    return _render_connector_edit(request, user=user, mode="create", original_connector_id="", form_data=_connector_form_payload(None), notice=notice, error=error, preview=None)


@app.get("/connectors/{connector_id}/edit", response_class=HTMLResponse)
def connector_edit_page(connector_id: str, request: Request, user=Depends(require_permissions("pipeline.run"))):
    spec = _get_connector_spec_or_404(connector_id)
    notice = request.query_params.get("notice") or ""
    error = request.query_params.get("error") or ""
    return _render_connector_edit(request, user=user, mode="edit", original_connector_id=spec.connector_id, form_data=_connector_form_payload(spec), notice=notice, error=error, preview=None)


@app.get("/connectors/runs/{connector_run_id}", response_class=HTMLResponse)
def connector_run_detail_page(connector_run_id: str, request: Request, user=Depends(require_permissions("pipeline.run")), conn=Depends(get_db)):
    run = get_connector_run(conn, tenant_id=user["tenant_id"], connector_run_id=connector_run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"error": f"connector_run_not_found: {connector_run_id}"})
    run_view = build_connector_run_view(run, artifacts_root=settings.artifacts_root)
    return _render(
        request,
        "connectors_run_detail.html",
        user=user,
        active="connectors",
        run=run_view,
    )


@app.get("/connectors/{connector_id}", response_class=HTMLResponse)
def connector_detail_page(connector_id: str, request: Request, user=Depends(require_permissions("pipeline.run")), conn=Depends(get_db)):
    spec = _get_connector_spec_or_404(connector_id)
    state = load_connector_state(project_root=settings.project_root, connector_id=spec.connector_id)
    bindings = describe_binding_sources(spec, project_root=settings.project_root, previous_state=state)
    health = connector_health_snapshot(spec, project_root=settings.project_root, previous_state=state)
    runs = list_connector_runs(conn, tenant_id=user["tenant_id"], connector_id=spec.connector_id, limit=50)
    bindings = enrich_binding_rows_with_run_history(bindings, runs)
    summary = summarize_connector_runs(runs)
    retry_policy = connector_retry_policy(spec)
    last_retryable = latest_retryable_run(runs)
    pending_recovery_jobs = list_connector_pending_jobs(conn, tenant_id=user["tenant_id"], config_path=str(spec.config_path), limit=25)
    recovery_analytics = summarize_recovery_analytics(runs, pending_recovery_jobs, queue_limit=settings.connector_recovery_queue_limit)
    recovery_decision = latest_recovery_decision(runs)
    notice = request.query_params.get("notice") or ""
    error = request.query_params.get("error") or ""
    return _render(
        request,
        "connectors_detail.html",
        user=user,
        active="connectors",
        spec=spec,
        bindings=bindings,
        runs=runs,
        state=state,
        summary=summary,
        health=health,
        retry_policy=retry_policy,
        last_retryable_run=last_retryable,
        pending_recovery_jobs=pending_recovery_jobs,
        recovery_analytics=recovery_analytics,
        recovery_decision=recovery_decision,
        notice=notice,
        error=error,
        schedule_samples=(health.get("next_due_slots") or []),
    )


@app.post("/connectors/preview", response_class=HTMLResponse)
async def connector_preview(
    request: Request,
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    form = await request.form()
    parsed = _connector_form_and_bindings_from_form(form)
    mode = parsed["mode"]
    original_connector_id = parsed["original_connector_id"]
    connector_id = parsed["connector_id"]
    kind = parsed["kind"]
    enabled = parsed["enabled"]
    description = parsed["description"]
    source_dir = parsed["source_dir"]
    schedule = parsed["schedule"]
    data_version_template = parsed["data_version_template"]
    bindings = parsed["bindings"]
    force = str(form.get("force_preview") or "").strip().lower() in {"1", "true", "on", "yes"}
    preview = None
    error = ""
    try:
        spec = save_connector_config(
            config_path=_connector_configs_dir() / f".__preview__{uuid.uuid4().hex[:8]}.yaml",
            project_root=settings.project_root,
            connector_id=connector_id,
            kind=kind,
            enabled=enabled,
            description=description or None,
            source_dir=source_dir or None,
            schedule=schedule or None,
            data_version_template=data_version_template or None,
            bindings=bindings,
            retry_policy=parsed["retry_policy"],
            preserve_unknown=False,
        )
        try:
            spec.config_path.unlink(missing_ok=True)
        except Exception:
            pass
        preview = preview_connector_spec(spec, project_root=settings.project_root, artifacts_root=settings.artifacts_root, force=force)
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get("tenant_id", "default"),
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="connector.config_preview",
            object_type="connector",
            object_id=connector_id or "preview",
            after={"kind": kind, "schedule": schedule, "predicted_status": preview.get("predicted_status"), "force": force},
            ip=ip,
            user_agent=ua,
            status="OK",
        )
    except Exception as e:
        error = str(e)
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get("tenant_id", "default"),
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="connector.config_preview",
            object_type="connector",
            object_id=connector_id or "preview",
            after={"kind": kind, "schedule": schedule, "force": force},
            ip=ip,
            user_agent=ua,
            status="FAIL",
            error=error,
        )
    return _render_connector_edit(
        request,
        user=user,
        mode=mode,
        original_connector_id=original_connector_id,
        form_data=parsed["form_data"],
        notice="preview_ready" if preview else "",
        error=error,
        preview=preview,
    )


@app.post("/connectors/save")
async def connector_save(
    request: Request,
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    form = await request.form()
    parsed = _connector_form_and_bindings_from_form(form)
    mode = parsed["mode"]
    original_connector_id = parsed["original_connector_id"]
    connector_id = parsed["connector_id"]
    kind = parsed["kind"]
    enabled = parsed["enabled"]
    description = parsed["description"]
    source_dir = parsed["source_dir"]
    schedule = parsed["schedule"]
    data_version_template = parsed["data_version_template"]
    bindings = parsed["bindings"]

    redirect_base = "/connectors/new" if mode == "create" else f"/connectors/{original_connector_id or connector_id}/edit"
    try:
        if mode == "edit":
            if not original_connector_id:
                raise ValueError("original_connector_id is required for edit mode")
            if connector_id != original_connector_id:
                raise ValueError("Renaming connector_id in UI is not supported yet")
        config_path = _config_path_for_connector_id(connector_id)
        spec = save_connector_config(
            config_path=config_path,
            project_root=settings.project_root,
            connector_id=connector_id,
            kind=kind,
            enabled=enabled,
            description=description or None,
            source_dir=source_dir or None,
            schedule=schedule or None,
            data_version_template=data_version_template or None,
            bindings=bindings,
            retry_policy=parsed["retry_policy"],
            preserve_unknown=(mode == "edit"),
        )
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get("tenant_id", "default"),
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="connector.config_save",
            object_type="connector",
            object_id=spec.connector_id,
            after={
                "mode": mode,
                "config_path": str(config_path.resolve()),
                "kind": spec.kind,
                "enabled": spec.enabled,
                "schedule": spec.schedule,
                "source_dir": spec.source_dir,
                "datasets": [b.dataset_key for b in spec.bindings],
            },
            ip=ip,
            user_agent=ua,
            status="OK",
        )
        return RedirectResponse(url=f"/connectors/{spec.connector_id}?notice=connector_saved", status_code=303)
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get("tenant_id", "default"),
            user_id=int(user.get("id", 0)),
            username=user.get("username", ""),
            role=user.get("role", ""),
            action="connector.config_save",
            object_type="connector",
            object_id=connector_id or original_connector_id or "new",
            after={"mode": mode},
            ip=ip,
            user_agent=ua,
            status="FAIL",
            error=str(e),
        )
        return RedirectResponse(url=f"{redirect_base}?error={str(e)[:200]}", status_code=303)


@app.post("/connectors/run")
def connectors_run_now(
    config_path: str = Form(...),
    redirect_to: str = Form("/connectors"),
    force: str = Form(""),
    dataset_keys: str = Form(""),
    trigger_override: str = Form(""),
    retry_parent_run_id: str = Form(""),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    try:
        force_flag = str(force or "").strip().lower() in {"1", "true", "on", "yes"}
        dataset_keys_list = [str(x).strip().lower() for x in str(dataset_keys or '').split(',') if str(x).strip()]
        spec = load_connector_spec(Path(config_path).resolve(), project_root=settings.project_root)
        trigger_type = "retry_failed" if dataset_keys_list else ("manual_force" if force_flag else "manual")
        override = str(trigger_override or '').strip().lower()
        if override in {"retry_failed", "retry_last_failed", "manual", "manual_force"}:
            trigger_type = override
        enqueue_connector_job(
            conn,
            tenant_id=user["tenant_id"],
            user_id=int(user["id"]),
            username=user["username"],
            config_path=config_path,
            trigger_type=trigger_type,
            force=force_flag,
            dataset_keys=dataset_keys_list,
            retry_parent_run_id=str(retry_parent_run_id or '').strip() or None,
        )
        base = redirect_to or f"/connectors/{spec.connector_id}"
        if dataset_keys_list:
            if trigger_type == 'retry_last_failed':
                notice = f"retry_last_failed_queued_{len(dataset_keys_list)}"
            else:
                notice = f"retry_failed_queued_{len(dataset_keys_list)}"
        else:
            notice = "connector_force_job_queued" if force_flag else "connector_job_queued"
        return RedirectResponse(url=f"{base}?notice={notice}", status_code=303)
    except Exception as e:
        base = redirect_to or "/connectors"
        return RedirectResponse(url=f"{base}?error={str(e)[:200]}", status_code=303)



@app.post("/connectors/recovery/cancel")
def connectors_cancel_recovery_job(
    request: Request,
    config_path: str = Form(...),
    job_id: int = Form(...),
    redirect_to: str = Form("/connectors"),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    spec = None
    try:
        spec = load_connector_spec(Path(config_path).resolve(), project_root=settings.project_root)
        pending = list_connector_pending_jobs(conn, tenant_id=user["tenant_id"], config_path=str(spec.config_path), limit=200)
        target = next((j for j in pending if int(j.get('job_id') or 0) == int(job_id) and is_recovery_trigger(j.get('trigger_type'))), None)
        if target is None:
            raise ValueError(f"Queued recovery job not found for connector={spec.connector_id}: job_id={job_id}")
        before_row = RunsRepo(conn).get_job(int(job_id))
        if not before_row:
            raise ValueError(f"Job not found: job_id={job_id}")
        before = dict(before_row)
        after = request_job_cancel(conn, int(job_id), reason=f"Connector recovery cancelled by {user.get('username')}")
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='connector.recovery_cancel',
            object_type='connector',
            object_id=spec.connector_id,
            before={
                'job_id': int(job_id),
                'trigger_type': target.get('trigger_type'),
                'dataset_keys': target.get('dataset_keys') or [],
                'retry_parent_run_id': target.get('retry_parent_run_id'),
                'job_status': before.get('status'),
            },
            after={
                'job_id': int(job_id),
                'job_status': (after or {}).get('status'),
                'dataset_keys': target.get('dataset_keys') or [],
                'retry_parent_run_id': target.get('retry_parent_run_id'),
            },
            ip=ip,
            user_agent=ua,
            status='OK',
        )
        base = redirect_to or f"/connectors/{spec.connector_id}"
        return RedirectResponse(url=f"{base}?notice=recovery_job_cancelled_{int(job_id)}", status_code=303)
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='connector.recovery_cancel',
            object_type='connector',
            object_id=(spec.connector_id if spec else str(config_path)),
            before={'job_id': int(job_id or 0)},
            ip=ip,
            user_agent=ua,
            status='FAIL',
            error=str(e),
        )
        base = redirect_to or (f"/connectors/{spec.connector_id}" if spec else '/connectors')
        return RedirectResponse(url=f"{base}?error={str(e)[:200]}", status_code=303)


@app.post("/connectors/recovery/clear")
def connectors_clear_recovery_queue(
    request: Request,
    config_path: str = Form(...),
    redirect_to: str = Form("/connectors"),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    spec = None
    try:
        spec = load_connector_spec(Path(config_path).resolve(), project_root=settings.project_root)
        pending = [
            j for j in list_connector_pending_jobs(conn, tenant_id=user['tenant_id'], config_path=str(spec.config_path), limit=200)
            if is_recovery_trigger(j.get('trigger_type'))
        ]
        if not pending:
            raise ValueError(f"No queued recovery jobs for connector={spec.connector_id}")
        cancelled_ids: list[int] = []
        for item in pending:
            after = request_job_cancel(conn, int(item['job_id']), reason=f"Connector recovery queue cleared by {user.get('username')}")
            if after is not None:
                cancelled_ids.append(int(item['job_id']))
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='connector.recovery_clear',
            object_type='connector',
            object_id=spec.connector_id,
            after={
                'cancelled_job_ids': cancelled_ids,
                'cancelled_jobs': len(cancelled_ids),
            },
            ip=ip,
            user_agent=ua,
            status='OK',
        )
        base = redirect_to or f"/connectors/{spec.connector_id}"
        return RedirectResponse(url=f"{base}?notice=recovery_queue_cleared_{len(cancelled_ids)}", status_code=303)
    except Exception as e:
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='connector.recovery_clear',
            object_type='connector',
            object_id=(spec.connector_id if spec else str(config_path)),
            ip=ip,
            user_agent=ua,
            status='FAIL',
            error=str(e),
        )
        base = redirect_to or (f"/connectors/{spec.connector_id}" if spec else '/connectors')
        return RedirectResponse(url=f"{base}?error={str(e)[:200]}", status_code=303)


@app.post("/connectors/run-slot")
def connectors_run_selected_slot(
    config_path: str = Form(...),
    scheduled_slot: str = Form(...),
    redirect_to: str = Form("/connectors"),
    force: str = Form(""),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    try:
        spec = load_connector_spec(Path(config_path).resolve(), project_root=settings.project_root)
        when = _parse_manual_schedule_slot(scheduled_slot, connector_id=spec.connector_id)
        slot = schedule_slot_for(when)
        if spec.schedule and not cron_matches(spec.schedule, when):
            raise ValueError(
                f"selected scheduled_slot is not due for connector={spec.connector_id} schedule='{spec.schedule}': {slot}"
            )
        force_flag = str(force or "").strip().lower() in {"1", "true", "on", "yes"}
        enqueue_connector_job(
            conn,
            tenant_id=user["tenant_id"],
            user_id=int(user["id"]),
            username=user["username"],
            config_path=config_path,
            trigger_type="schedule_manual",
            schedule_slot=slot,
            force=force_flag,
        )
        base = redirect_to or f"/connectors/{spec.connector_id}"
        return RedirectResponse(url=f"{base}?notice=scheduled_slot_queued", status_code=303)
    except Exception as e:
        base = redirect_to or "/connectors"
        return RedirectResponse(url=f"{base}?error={str(e)[:200]}", status_code=303)


@app.post("/connectors/upload")
def connectors_upload_file(
    request: Request,
    config_path: str = Form(...),
    dataset_key: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(require_permissions("upload.create", "pipeline.run")),
    conn=Depends(get_db),
):
    try:
        spec = load_connector_spec(Path(config_path).resolve(), project_root=settings.project_root)
        binding = get_binding(spec, dataset_key)
        if binding is None:
            raise ValueError(f"dataset_key '{dataset_key}' is not configured for connector {spec.connector_id}")
        if not file or not (file.filename or '').strip():
            raise ValueError(f"No upload file provided for connector={spec.connector_id} dataset={dataset_key}")
        target = resolve_upload_target(spec, binding, project_root=settings.project_root, original_name=file.filename or 'upload.csv')
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            written = save_upload_limited(file.file, dest=target, max_bytes=settings.max_upload_bytes)
        except ValueError as e:
            if str(e) == 'upload_too_large':
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл слишком большой. Лимит: {settings.max_upload_bytes // (1024 * 1024)} MB",
                )
            raise
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='connector.upload',
            object_type='connector',
            object_id=spec.connector_id,
            after={
                'dataset_key': binding.dataset_key,
                'config_path': str(Path(config_path).resolve()),
                'target_path': str(target),
                'bytes': int(written),
                'original_filename': file.filename or '',
            },
            ip=ip,
            user_agent=ua,
            status='OK',
        )
        return RedirectResponse(url=f"/connectors/{spec.connector_id}?notice=uploaded_{binding.dataset_key}", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        try:
            spec = load_connector_spec(Path(config_path).resolve(), project_root=settings.project_root)
            object_id = spec.connector_id
        except Exception:
            object_id = str(config_path)
        ip, ua = _get_ip_ua(request)
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='connector.upload',
            object_type='connector',
            object_id=object_id,
            after={'dataset_key': str(dataset_key or '').strip()},
            ip=ip,
            user_agent=ua,
            status='FAIL',
            error=str(e),
        )
        return RedirectResponse(url=f"/connectors?error={str(e)[:200]}", status_code=303)


@app.post("/connectors/schedule/tick")
def connectors_schedule_tick(
    at: str = Form(""),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    try:
        when = datetime.fromisoformat(at) if str(at or "").strip() else datetime.now(timezone.utc)
        res = schedule_due_connector_jobs(
            conn,
            tenant_id=user["tenant_id"],
            user_id=int(user["id"]),
            username=user["username"],
            configs_dir=_connector_configs_dir(),
            when=when,
        )
        return RedirectResponse(url=f"/connectors?notice=enqueued_{len(res.get('enqueued') or [])}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/connectors?error={str(e)[:200]}", status_code=303)


@app.get("/api/contracts/catalog")
def api_contracts_catalog(
    request: Request,
    q: str = "",
    domain: str = "",
    status: str = "",
    source: str = "",
    user=Depends(get_current_user),
):
    manifest = _load_contract_catalog_manifest()
    rows = _filter_contract_catalog_rows(manifest, q=q, domain=domain, status=status, source=source)
    source_norm = str(source or "").strip().lower()
    filtered_rows = []
    for row in rows:
        item = dict(row)
        template_rows = [dict(x) for x in (row.get("mapping_template_rows") or []) if isinstance(x, dict)]
        if source_norm:
            template_rows = [x for x in template_rows if str(x.get("source_system") or "").strip().lower() == source_norm]
        item["mapping_template_rows"] = template_rows
        item["mapping_template_count"] = len(template_rows)
        filtered_rows.append(item)
    return {
        "schema": manifest.get("schema"),
        "generated_at_utc": manifest.get("generated_at_utc"),
        "dataset_count": manifest.get("dataset_count"),
        "filtered_count": len(filtered_rows),
        "filters": {"q": q, "domain": domain, "status": status, "source": source},
        "domains": manifest.get("domains") or [],
        "statuses": manifest.get("statuses") or [],
        "source_systems": manifest.get("source_systems") or [],
        "datasets": filtered_rows,
    }


@app.get("/contracts", response_class=HTMLResponse)
def contracts_page(
    request: Request,
    q: str = "",
    domain: str = "",
    status: str = "",
    source: str = "",
    focus: str = "",
    user=Depends(get_current_user),
):
    return _render(request, "contracts.html", **_build_contract_catalog_context(user=user, q=q, domain=domain, status=status, source=source, focus=focus))


@app.get("/api/contracts/validation-report")
def api_contract_validation_report(
    path: str,
    dataset: str = "",
    source: str = "",
    data_version: str = "",
    user=Depends(get_current_user),
):
    ctx = _build_contract_validation_report_context(user=user, path=path, dataset=dataset, source=source, data_version=data_version)
    return {
        'schema': ctx['report'].get('schema'),
        'report_virtual_path': ctx['report_virtual_path'],
        'dataset_name': ctx['dataset_name'],
        'dataset_key': ctx['dataset_key'],
        'source': ctx['source'],
        'data_version': ctx['data_version'],
        'contract_href': ctx['contract_href'],
        'report': ctx['report'],
        'issues': ctx['issues'],
    }


@app.get("/contracts/validation-report", response_class=HTMLResponse)
def contract_validation_report_page(
    request: Request,
    path: str,
    dataset: str = "",
    source: str = "",
    data_version: str = "",
    user=Depends(get_current_user),
):
    return _render(
        request,
        "contract_validation_report.html",
        **_build_contract_validation_report_context(user=user, path=path, dataset=dataset, source=source, data_version=data_version),
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, user=Depends(get_current_user)):
    return _render(request, "upload.html", **_build_upload_page_context(user=user))


@app.post("/upload/ingest-all")
def ingest_all(
    request: Request,
    data_version: str = Form(...),
    farms_file: Optional[UploadFile] = File(None),
    animals_file: Optional[UploadFile] = File(None),
    lactations_file: Optional[UploadFile] = File(None),
    farms_mapping_path: str = Form("configs/mappings/farms_example.yaml"),
    animals_mapping_path: str = Form("configs/mappings/animals_example.yaml"),
    lactations_mapping_path: str = Form("configs/mappings/lactations_example.yaml"),
    farms_mapping_upload: Optional[UploadFile] = File(None),
    animals_mapping_upload: Optional[UploadFile] = File(None),
    lactations_mapping_upload: Optional[UploadFile] = File(None),
    user=Depends(require_permissions("upload.create", "pipeline.run")),
    conn=Depends(get_db),
):
    contracts = load_contracts_dir(safe_join(settings.project_root, "configs/contracts"))
    ip, ua = _get_ip_ua(request)

    def save_upload(up: UploadFile) -> Path:
        suffix = Path(up.filename or "upload").suffix
        dest = settings.uploads_dir / f"{uuid.uuid4().hex}{suffix}"
        try:
            save_upload_limited(up.file, dest=dest, max_bytes=settings.max_upload_bytes)
        except ValueError as e:
            if str(e) == "upload_too_large":
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл слишком большой. Лимит: {settings.max_upload_bytes // (1024*1024)} MB",
                )
            raise
        return dest

    def save_mapping_upload(up: UploadFile) -> Path:
        suffix = Path(up.filename or "mapping").suffix
        dest = settings.uploads_dir / f"{uuid.uuid4().hex}{suffix}"
        try:
            save_upload_limited(up.file, dest=dest, max_bytes=settings.max_mapping_bytes)
        except ValueError as e:
            if str(e) == "upload_too_large":
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл маппинга слишком большой. Лимит: {settings.max_mapping_bytes // (1024*1024)} MB",
                )
            raise
        return dest

    def resolve_mapping(selected_path: str, uploaded: Optional[UploadFile]) -> Path:
        if uploaded and uploaded.filename:
            return save_mapping_upload(uploaded)
        return safe_join(settings.project_root, selected_path)

    jobs_created: list[str] = []
    contract_errors: list[dict] = []
    upload_check_run_id = f"uploadcheck_{uuid.uuid4().hex[:12]}"

    def validate_and_enqueue(dataset_key: str, file_up: Optional[UploadFile], mapping_sel: str, mapping_up: Optional[UploadFile]):
        if not file_up or not file_up.filename:
            return
        file_path = save_upload(file_up)
        mapping_path = resolve_mapping(mapping_sel, mapping_up)
        contract_name = dataset_contract_name(dataset_key)
        contract = contracts.get(contract_name or '')
        if contract is None:
            raise HTTPException(status_code=500, detail=f"Не найден контракт для dataset_key={dataset_key}")
        validation = validate_source_by_contract(
            dataset_key=dataset_key,
            file_path=file_path,
            mapping_path=mapping_path,
            contract=contract,
        )
        audit_after = {
            'dataset_key': dataset_key,
            'contract_name': contract.dataset,
            'contract_version': contract.contract_version,
            'source_file': str(file_path),
            'mapping_file': str(mapping_path),
            'rows_in': validation.rows_in,
            'error_count': validation.error_count,
            'preview': validation.top_messages(limit=5),
            'data_version': data_version,
        }
        write_audit(
            conn,
            tenant_id=user.get('tenant_id', 'default'),
            user_id=int(user.get('id', 0)),
            username=user.get('username', ''),
            role=user.get('role', ''),
            action='contract.validate',
            object_type='dataset',
            object_id=contract.dataset,
            data_version=data_version,
            before=None,
            after=audit_after,
            ip=ip,
            user_agent=ua,
            status='OK' if validation.ok else 'FAIL',
            error=None if validation.ok else '; '.join(validation.top_messages(limit=3))[:1000],
        )
        if not validation.ok:
            report_dir = settings.artifacts_root / data_version / 'contract_precheck' / upload_check_run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f'contract_validation_{contract.dataset}.json'
            report_payload = validation.to_dict(preview_limit=50)
            report_payload['data_version'] = data_version
            report_payload['source'] = 'upload'
            report_payload['upload_check_run_id'] = upload_check_run_id
            write_json(report_path, report_payload)
            report_virtual_path, _ = _virtualize_artifact_path(str(report_path))
            contract_errors.append({
                'dataset_key': dataset_key,
                'dataset': contract.dataset,
                'contract_version': contract.contract_version,
                'error_count': validation.error_count,
                'rows_in': validation.rows_in,
                'mapping_file': str(mapping_path),
                'mapping_file_virtual': _virtualize_artifact_path(str(mapping_path))[0],
                'preview': validation.top_messages(limit=12),
                'report_path': str(report_path),
                'report_virtual_path': report_virtual_path,
                'report_href': f"/contracts/validation-report?{urlencode({'path': report_virtual_path, 'dataset': contract.dataset, 'source': 'upload', 'data_version': data_version})}",
                'contract_href': _contract_focus_href(contract.dataset),
            })
            return
        job_request = build_ingest_job_request(
            dataset_key=dataset_key,
            file_path=file_path,
            mapping_path=mapping_path,
            data_version=data_version,
            artifacts_root=settings.artifacts_root,
            contracts_dir=safe_join(settings.project_root, "configs/contracts"),
        )
        job_id = enqueue_pipeline_job(
            conn,
            request=job_request,
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            username=user["username"],
            logs_dir=settings.logs_dir,
        )
        jobs_created.append(job_id)
        _audit_pipeline_enqueue(
            conn,
            user=user,
            job_id=job_id,
            kind=job_request.kind,
            object_id=job_request.object_id,
            extra_after=job_request.extra_after,
        )

    validate_and_enqueue("farms", farms_file, farms_mapping_path, farms_mapping_upload)
    validate_and_enqueue("animals", animals_file, animals_mapping_path, animals_mapping_upload)
    validate_and_enqueue("lactations", lactations_file, lactations_mapping_path, lactations_mapping_upload)

    if contract_errors:
        status_code = 400 if not jobs_created else 200
        notice = ""
        if jobs_created:
            notice = f"Часть файлов прошла contract validation и была поставлена в очередь: {len(jobs_created)} job(s)."
        response = _render(
            request,
            "upload.html",
            **_build_upload_page_context(
                user=user,
                contract_errors=contract_errors,
                created_jobs=jobs_created,
                data_version=data_version,
                notice=notice,
            ),
        )
        response.status_code = status_code
        return response

    return RedirectResponse(url="/tasks", status_code=302)


@app.get("/qc", response_class=HTMLResponse)
def qc_page(request: Request, user=Depends(get_current_user)):
    dvs = list_data_versions(settings.artifacts_root)
    selected = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    qc_runs = list_qc_runs(settings.artifacts_root, selected) if selected else []
    return _render(request, "qc.html", user=user, data_versions=dvs, selected_dv=selected, qc_runs=qc_runs)


@app.post("/qc/run")
def qc_run(
    data_version: str = Form(...),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    job_request = build_qc_job_request(
        data_version=data_version,
        artifacts_root=settings.artifacts_root,
        contracts_dir=safe_join(settings.project_root, "configs/contracts"),
    )
    job_id = enqueue_pipeline_job(
        conn,
        request=job_request,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        username=user["username"],
        logs_dir=settings.logs_dir,
    )
    _audit_pipeline_enqueue(conn, user=user, job_id=job_id, kind=job_request.kind, object_id=job_request.object_id, extra_after=job_request.extra_after)
    return RedirectResponse(url="/tasks", status_code=302)


@app.get("/train", response_class=HTMLResponse)
def train_page(request: Request, user=Depends(get_current_user)):
    dvs = list_data_versions(settings.artifacts_root)
    dv = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    qc_runs = list_qc_runs(settings.artifacts_root, dv) if dv else []
    selected_qc = request.query_params.get("qc") or (qc_runs[-1] if qc_runs else "")
    models = list_model_versions(settings.artifacts_root, dv) if dv else []
    model_entries = list_model_entries(settings.artifacts_root, dv) if dv else []
    selected_model_version_input = request.query_params.get("model_version") or ""
    selected_config_path = request.query_params.get("config") or str(default_ml_config_path())
    return _render(
        request,
        "train.html",
        user=user,
        data_versions=dvs,
        selected_dv=dv,
        qc_runs=qc_runs,
        selected_qc=selected_qc,
        model_versions=models,
        model_entries=model_entries,
        selected_model_version_input=selected_model_version_input,
        selected_config_path=selected_config_path,
    )


@app.post("/train/run")
def train_run(
    data_version: str = Form(...),
    qc_run: str = Form(...),
    model_version: str = Form(""),
    config_path: str = Form(""),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    mv = str(model_version or "").strip() or None
    cfg = str(config_path or "").strip() or None
    job_request = build_train_job_request(
        data_version=data_version,
        qc_run=qc_run,
        artifacts_root=settings.artifacts_root,
        model_version=mv,
        config_path=Path(cfg) if cfg else None,
    )
    job_id = enqueue_pipeline_job(
        conn,
        request=job_request,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        username=user["username"],
        logs_dir=settings.logs_dir,
    )
    _audit_pipeline_enqueue(conn, user=user, job_id=job_id, kind=job_request.kind, object_id=job_request.object_id, extra_after=job_request.extra_after)
    return RedirectResponse(url="/tasks", status_code=302)


@app.get("/score", response_class=HTMLResponse)
def score_page(request: Request, user=Depends(get_current_user)):
    dvs = list_data_versions(settings.artifacts_root)
    dv = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    models = list_model_versions(settings.artifacts_root, dv) if dv else []
    selected_model = request.query_params.get("mv") or (models[-1] if models else "")
    scorings = list_scoring_runs(settings.artifacts_root, dv) if dv else []
    scoring_entries = list_scoring_entries(settings.artifacts_root, dv) if dv else []
    selected_scoring_run_input = request.query_params.get("scoring_run") or ""
    selected_config_path = request.query_params.get("config") or str(default_ml_config_path())
    return _render(
        request,
        "score.html",
        user=user,
        data_versions=dvs,
        selected_dv=dv,
        model_versions=models,
        selected_model=selected_model,
        scoring_runs=scorings,
        scoring_entries=scoring_entries,
        selected_scoring_run_input=selected_scoring_run_input,
        selected_config_path=selected_config_path,
    )


@app.post("/score/run")
def score_run(
    data_version: str = Form(...),
    model_version: str = Form(...),
    scoring_run: str = Form(""),
    config_path: str = Form(""),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    sr = str(scoring_run or "").strip() or None
    cfg = str(config_path or "").strip() or None
    job_request = build_score_job_request(
        data_version=data_version,
        model_version=model_version,
        artifacts_root=settings.artifacts_root,
        scoring_run=sr,
        config_path=Path(cfg) if cfg else None,
    )
    job_id = enqueue_pipeline_job(
        conn,
        request=job_request,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        username=user["username"],
        logs_dir=settings.logs_dir,
    )
    _audit_pipeline_enqueue(conn, user=user, job_id=job_id, kind=job_request.kind, object_id=job_request.object_id, extra_after=job_request.extra_after)
    return RedirectResponse(url="/tasks", status_code=302)


def _csv_preview(path: Path, limit: int = 20) -> list[SimpleNamespace]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[SimpleNamespace] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            if i >= limit:
                break
            rows.append(SimpleNamespace(**r))
    return rows


@app.get("/repro", response_class=HTMLResponse)
def repro_page(request: Request, user=Depends(require_permissions("kpi.view"))):
    dvs = list_data_versions(settings.artifacts_root)
    dv = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    asof = request.query_params.get("asof") or utc_date_str()
    runs = list_repro_runs(settings.artifacts_root, dv) if dv else []
    last = (runs[-1] if runs else "")

    kpis_preview: list[SimpleNamespace] = []
    wl_preview: list[SimpleNamespace] = []
    if dv and last:
        base = settings.artifacts_root / dv / "repro" / "runs" / last
        kpis_preview = _csv_preview(base / "repro_kpis_farm.csv", limit=20)
        wl_preview = _csv_preview(base / "repro_worklists.csv", limit=30)

    return _render(
        request,
        "repro.html",
        user=user,
        active="repro",
        data_versions=dvs,
        selected_dv=dv,
        asof_date=asof,
        repro_runs=runs,
        kpis_preview=kpis_preview,
        worklists_preview=wl_preview,
    )


@app.post("/repro/run")
def repro_run(
    data_version: str = Form(...),
    asof_date: str = Form(...),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    job_request = build_repro_job_request(
        data_version=data_version,
        asof_date=asof_date,
        cfg_path=safe_join(settings.project_root, "configs/repro/repro_rules_v1.yaml"),
        artifacts_root=settings.artifacts_root,
    )
    job_id = enqueue_pipeline_job(
        conn,
        request=job_request,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        username=user["username"],
        logs_dir=settings.logs_dir,
    )
    _audit_pipeline_enqueue(conn, user=user, job_id=job_id, kind=job_request.kind, object_id=job_request.object_id, extra_after=job_request.extra_after)
    return RedirectResponse(url="/tasks", status_code=302)


@app.get("/api/copilot/fact")
def api_copilot_fact_target(
    request: Request,
    target: str = "",
    data_version: str = "",
    section: str = "",
    table: str = "",
    metric: str = "",
    run_id: str = "",
    report_version: str = "",
    fact_id: str = "",
    source_id: str = "",
    request_id: str = "",
    user=Depends(get_current_user),
):
    ctx = _build_copilot_resolver_context(
        request=request,
        user=user,
        target=target,
        data_version=data_version,
        section=section,
        table=table,
        metric=metric,
        run_id=run_id,
        report_version=report_version,
        fact_id=fact_id,
        source_id=source_id,
        request_id=request_id,
    )
    return _copilot_target_api_payload(ctx)


@app.get("/copilot/fact", response_class=HTMLResponse)
def copilot_fact_target_page(
    request: Request,
    target: str = "",
    data_version: str = "",
    section: str = "",
    table: str = "",
    metric: str = "",
    run_id: str = "",
    report_version: str = "",
    fact_id: str = "",
    source_id: str = "",
    request_id: str = "",
    user=Depends(get_current_user),
):
    return _render(
        request,
        "copilot_fact.html",
        **_build_copilot_resolver_context(
            request=request,
            user=user,
            target=target,
            data_version=data_version,
            section=section,
            table=table,
            metric=metric,
            run_id=run_id,
            report_version=report_version,
            fact_id=fact_id,
            source_id=source_id,
            request_id=request_id,
        ),
    )


@app.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    user=Depends(require_permissions(rbac.PERM_REPORTS_VIEW)),
    conn=Depends(get_db),
):
    dvs = list_data_versions(settings.artifacts_root)
    dv = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    qc_runs = list_qc_runs(settings.artifacts_root, dv) if dv else []
    models = list_model_versions(settings.artifacts_root, dv) if dv else []
    scorings = list_scoring_runs(settings.artifacts_root, dv) if dv else []
    reports = list_report_versions(settings.artifacts_root, dv) if dv else []

    statuses = list_report_statuses(conn, tenant_id=user.get("tenant_id", "default"), data_version=dv, report_versions=reports)

    return _render(
        request,
        "reports.html",
        user=user,
        data_versions=dvs,
        selected_dv=dv,
        qc_runs=qc_runs,
        model_versions=models,
        scoring_runs=scorings,
        report_versions=reports,
        report_statuses=statuses,
        default_mode="fallback",
    )


@app.post("/reports/run")
def reports_run(
    data_version: str = Form(...),
    qc_run: str = Form(...),
    model_version: str = Form(...),
    scoring_run: str = Form(...),
    mode: str = Form("fallback"),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    job_request = build_report_job_request(
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode=mode,
        artifacts_root=settings.artifacts_root,
    )
    job_id = enqueue_pipeline_job(
        conn,
        request=job_request,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        username=user["username"],
        logs_dir=settings.logs_dir,
    )
    _audit_pipeline_enqueue(conn, user=user, job_id=job_id, kind=job_request.kind, object_id=job_request.object_id, extra_after=job_request.extra_after)
    return RedirectResponse(url="/tasks", status_code=302)


@app.get("/decisions", response_class=HTMLResponse)
def decisions_page(request: Request, user=Depends(get_current_user)):
    dvs = list_data_versions(settings.artifacts_root)
    dv = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    scorings = list_scoring_runs(settings.artifacts_root, dv) if dv else []
    return _render(request, "decisions.html", user=user, data_versions=dvs, selected_dv=dv, scoring_runs=scorings)


@app.post("/decisions/init")
def decisions_init(
    data_version: str = Form(...),
    scoring_run: str = Form(""),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    log_path = settings.logs_dir / f"job_{uuid.uuid4().hex}.log"
    argv = [
        "decision",
        "init",
        "--data-version",
        data_version,
        "--user",
        user["username"],
        "--artifacts",
        str(settings.artifacts_root),
    ]
    if scoring_run:
        argv += ["--scoring-run", scoring_run]

    create_job(conn, kind="decision_init", tenant_id=user["tenant_id"], user_id=user["id"], user=user["username"], command="python -m genomeai", args={"argv": argv}, log_path=log_path)
    write_audit(
        conn,
        tenant_id=user.get('tenant_id','default'),
        user_id=int(user.get('id',0)),
        username=user.get('username',''),
        role=user.get('role',''),
        action='decisions.init',
        object_type='decision',
        object_id=locals().get('animal_id','') if 'animal_id' in locals() else None,
        after={'data_version': locals().get('data_version','')},
        status='OK',
    )
    return RedirectResponse(url="/tasks", status_code=302)


@app.post("/decisions/add")
def decisions_add(
    data_version: str = Form(...),
    animal_id: str = Form(...),
    lactation_id: str = Form(...),
    recommendation_type: str = Form(...),
    decision: str = Form(...),
    comment: str = Form(""),
    scoring_run: str = Form(""),
    user=Depends(require_permissions("decisions.write")),
    conn=Depends(get_db),
):
    log_path = settings.logs_dir / f"job_{uuid.uuid4().hex}.log"
    argv = [
        "decision",
        "add",
        "--data-version",
        data_version,
        "--animal-id",
        animal_id,
        "--lactation-id",
        lactation_id,
        "--recommendation-type",
        recommendation_type,
        "--decision",
        decision,
        "--comment",
        comment,
        "--user",
        user["username"],
        "--artifacts",
        str(settings.artifacts_root),
    ]
    if scoring_run:
        argv += ["--scoring-run", scoring_run]

    create_job(conn, kind="decision_add", tenant_id=user["tenant_id"], user_id=user["id"], user=user["username"], command="python -m genomeai", args={"argv": argv}, log_path=log_path)
    write_audit(
        conn,
        tenant_id=user.get('tenant_id','default'),
        user_id=int(user.get('id',0)),
        username=user.get('username',''),
        role=user.get('role',''),
        action='decisions.add',
        object_type='decision',
        object_id=locals().get('animal_id','') if 'animal_id' in locals() else None,
        after={'data_version': locals().get('data_version','')},
        status='OK',
    )
    return RedirectResponse(url="/tasks", status_code=302)






# --- T12-03: Playbooks UI ---

@app.get("/playbooks", response_class=HTMLResponse)
def playbooks_page(request: Request, user=Depends(require_permissions("playbooks.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    target_kind = (request.query_params.get("target_kind") or "").strip() or None
    target_type = (request.query_params.get("target_type") or "").strip() or None
    farm_id = (request.query_params.get("farm_id") or "").strip() if request.query_params.get("farm_id") is not None else None

    notice = request.query_params.get("notice")
    error = request.query_params.get("error")

    view_version_id = (request.query_params.get("view_version_id") or "").strip() or None
    clone_version_id = (request.query_params.get("clone_version_id") or "").strip() or None

    from .playbooks_v1 import list_versions, get_version

    versions = []
    active_pb = None
    try:
        versions = list_versions(conn, tenant_id=tenant_id, target_kind=target_kind, target_type=target_type, farm_id=farm_id, limit=200, offset=0)
    except Exception as e:
        error = f"Не удалось загрузить версии: {e}"

    if target_kind and target_type:
        active_pb = _get_recommended_playbook_for_alert(conn, tenant_id=tenant_id, alert={"alert_type": target_type, "why": {"farm_id": farm_id}}) if target_kind=='alert' else _get_recommended_playbook_for_task(conn, tenant_id=tenant_id, task={"task_type": target_type, "why": {"farm_id": farm_id}})

    view_pb = None
    draft = None
    if view_version_id:
        view_pb = get_version(conn, tenant_id=tenant_id, version_id=view_version_id)
    if clone_version_id:
        src = get_version(conn, tenant_id=tenant_id, version_id=clone_version_id)
        if src:
            steps = list(src.get("steps") or [])
            step_titles = [str(s.get("title") or "") for s in steps][:8]
            step_details = [str(s.get("details") or "") for s in steps][:8]
            required_idx = [i + 1 for i, s in enumerate(steps[:8]) if bool(s.get("required"))]
            draft = SimpleNamespace(
                name=str(src.get("name") or "") + " (копия)",
                description=str(src.get("description") or ""),
                step_titles=step_titles + [""] * max(0, 8 - len(step_titles)),
                step_details=step_details + [""] * max(0, 8 - len(step_details)),
                required_idx=required_idx,
            )

    can_write = ("playbooks.write" in set(user.get("permissions") or []))
    filters = SimpleNamespace(target_kind=target_kind or "", target_type=target_type or "", farm_id=farm_id or "")
    return _render(
        request,
        "playbooks.html",
        user=user,
        versions=versions,
        active_playbook=active_pb,
        view_playbook=view_pb,
        draft=draft,
        can_write=can_write,
        filters=filters,
        notice=notice,
        error=error,
    )


@app.post("/playbooks/create")
def playbooks_create(
    request: Request,
    target_kind: str = Form(...),
    target_type: str = Form(...),
    farm_id: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    comment: str = Form(""),
    set_active: str = Form("1"),
    steps_json: str = Form(""),
    step_title: list[str] = Form([]),
    step_details: list[str] = Form([]),
    step_required: list[str] = Form([]),
    user=Depends(require_permissions("playbooks.write")),
    conn=Depends(get_db),
):
    from .playbooks_v1 import PlaybookCreate, create_playbook_version, get_active_version_state, make_playbook_key

    tenant_id = user.get("tenant_id", "default")

    # Steps input (UI): either legacy JSON textarea (steps_json) OR table rows (step_title/step_details)
    steps = []
    if (steps_json or "").strip():
        try:
            steps = json.loads(steps_json)
        except Exception as e:
            q = f"target_kind={target_kind}&target_type={target_type}&farm_id={farm_id}".strip('&')
            return RedirectResponse(url=f"/playbooks?{q}&error=steps_json_parse_error:{str(e)[:200]}", status_code=303)
        if not isinstance(steps, list):
            q = f"target_kind={target_kind}&target_type={target_type}&farm_id={farm_id}".strip('&')
            return RedirectResponse(url=f"/playbooks?{q}&error=steps_must_be_list", status_code=303)
    else:
        req_set = set([str(x) for x in (step_required or [])])
        titles = list(step_title or [])
        details = list(step_details or [])
        # ensure consistent length
        n = max(len(titles), len(details))
        titles += [""] * max(0, n - len(titles))
        details += [""] * max(0, n - len(details))
        for i, (t, d) in enumerate(list(zip(titles, details))[:8], start=1):
            t = str(t or "").strip()
            if not t:
                continue
            steps.append({"title": t, "details": str(d or "").strip(), "required": (str(i) in req_set)})

    pb = PlaybookCreate(
        target_kind=str(target_kind),
        target_type=str(target_type),
        farm_id=str(farm_id or ""),
        name=str(name or ""),
        description=str(description or ""),
        steps=steps,
        comment=str(comment or ""),
        set_active=(str(set_active).strip() not in ("0", "false", "False")),
    )

    playbook_key = None
    before_active = None
    try:
        playbook_key = make_playbook_key(target_kind=pb.target_kind, target_type=pb.target_type)
        before_active = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=pb.farm_id or "")

        vid = create_playbook_version(conn, tenant_id=tenant_id, pb=pb, created_by=int(user.get("id", 0)) or None, created_by_username=str(user.get("username", "")) or None)
    except Exception as e:
        q = f"target_kind={target_kind}&target_type={target_type}&farm_id={farm_id}".strip('&')
        return RedirectResponse(url=f"/playbooks?{q}&error={str(e)[:200]}", status_code=303)

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="playbooks_v1.create_version",
        object_type="playbook",
        object_id=str(vid),
        before={"active": before_active, "playbook_key": playbook_key},
        after={"playbook_key": playbook_key, "target_kind": pb.target_kind, "target_type": pb.target_type, "farm_id": pb.farm_id, "name": pb.name, "set_active": bool(pb.set_active), "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    q = f"target_kind={target_kind}&target_type={target_type}&farm_id={farm_id}".strip('&')
    return RedirectResponse(url=f"/playbooks?{q}&notice=created", status_code=303)


@app.post("/playbooks/activate")
def playbooks_activate(
    request: Request,
    version_id: str = Form(...),
    playbook_key: str = Form(...),
    farm_id: str = Form(""),
    user=Depends(require_permissions("playbooks.write")),
    conn=Depends(get_db),
):
    from .playbooks_v1 import get_active_version_state, set_active_playbook

    tenant_id = user.get("tenant_id", "default")
    before = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id)

    try:
        set_active_playbook(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id, version_id=version_id)
    except Exception as e:
        return RedirectResponse(url=f"/playbooks?error={str(e)[:200]}", status_code=303)

    after = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id)

    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="playbooks_v1.activate",
        object_type="playbook",
        object_id=str(version_id),
        before={"active": before, "playbook_key": playbook_key, "farm_id": farm_id},
        after={"active": after, "playbook_key": playbook_key, "farm_id": farm_id, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )

    return RedirectResponse(url=f"/playbooks?notice=activated&target_kind={playbook_key.split(':')[0]}&target_type={':'.join(playbook_key.split(':')[1:])}&farm_id={farm_id}", status_code=303)


# --- T12-03: Workflow UI (tasks with playbooks) ---

@app.get("/workflow", response_class=HTMLResponse)
def workflow_page(request: Request, user=Depends(require_permissions("tasks.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    status = (request.query_params.get("status") or "").strip() or None
    task_type = (request.query_params.get("task_type") or "").strip() or None
    stage = (request.query_params.get("stage") or "").strip() or None
    q = (request.query_params.get("q") or "").strip() or None

    try:
        listing = workflow_listing_use_case(
            conn=conn,
            tenant_id=tenant_id,
            status=status,
            task_type=task_type,
            stage=stage,
            q=q,
            limit=200,
            offset=0,
        )
    except ValueError:
        listing = {
            "total": 0,
            "tasks": [],
            "filters": SimpleNamespace(status=status or "", task_type=task_type or "", stage=stage or "", q=q or ""),
            "task_statuses": list(task_status_options()),
            "stage_options": [""],
        }

    tasks = list(listing.get("tasks") or [])
    for t in tasks:
        pb = _get_recommended_playbook_for_task(conn, tenant_id=tenant_id, task=t)
        if pb:
            t["playbook_name"] = pb.get("name")
            t["playbook_version_id"] = pb.get("version_id")
        else:
            t["playbook_name"] = None
            t["playbook_version_id"] = None

    return _render(
        request,
        "workflow.html",
        user=user,
        tasks=tasks,
        total=int(listing.get("total") or 0),
        filters=(listing.get("filters") or SimpleNamespace(status=status or "", task_type=task_type or "", stage=stage or "", q=q or "")),
        task_statuses=list(listing.get("task_statuses") or list(task_status_options())),
        stage_options=list(listing.get("stage_options") or [""]),
    )


@app.get("/workflow/{task_id}", response_class=HTMLResponse)
def workflow_task_page(task_id: str, request: Request, user=Depends(require_permissions("tasks.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    t = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    if not t:
        raise HTTPException(404)
    pb = _get_recommended_playbook_for_task(conn, tenant_id=tenant_id, task=t)
    return _render(request, "task_detail.html", user=user, task=t, playbook=pb)


# --- T12-04: Weekly Plans UI (approve/reject director + auto tasks) ---


@app.get("/weekly_plans", response_class=HTMLResponse)
def weekly_plans_page(request: Request, user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_VIEW)), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    status = (request.query_params.get("status") or "").strip() or None
    q = (request.query_params.get("q") or "").strip() or None
    error = (request.query_params.get("error") or "").strip() or None
    notice = (request.query_params.get("notice") or "").strip() or None

    try:
        res = list_weekly_plans(conn, tenant_id=tenant_id, status=status, q=q, limit=200, offset=0)
    except Exception as e:
        res = {"total": 0, "weekly_plans": []}
        error = error or str(e)

    today = utc_date()
    week_start = (today - timedelta(days=today.weekday())).isoformat()

    filters = SimpleNamespace(status=status or "", q=q or "")
    perms = set(user.get("permissions") or [])
    can_write = (rbac.PERM_WEEKLY_PLANS_WRITE in perms)
    can_approve = (rbac.PERM_WEEKLY_PLANS_APPROVE in perms)
    pending_res = {"total": 0, "weekly_plans": []}
    if can_approve:
        try:
            pending_res = list_pending_approval_weekly_plans(conn, tenant_id=tenant_id, limit=50, offset=0)
        except Exception as e:
            error = error or str(e)
    return _render(
        request,
        "weekly_plans.html",
        user=user,
        weekly_plans=list(res.get("weekly_plans") or []),
        total=int(res.get("total") or 0),
        pending_weekly_plans=[summarize_weekly_plan(p) for p in list(pending_res.get("weekly_plans") or [])],
        pending_total=int(pending_res.get("total") or 0),
        filters=filters,
        can_write=can_write,
        can_approve=can_approve,
        default_week_start=week_start,
        default_generate_question="Сформируй план на неделю",
        error=error,
        notice=notice,
        active="weekly_plans",
    )


def _parse_actions_lines(text: str) -> list[dict]:
    out: list[dict] = []
    for line in (text or "").splitlines():
        t = str(line).strip()
        if not t:
            continue
        out.append({"title": t})
    return out


def _generate_weekly_plan_payload(*, data_version: str, week_start: str, question: str, farm_id: str | None = None) -> dict:
    dv = str(data_version or "").strip()
    if not dv:
        raise ValueError("data_version пуст")
    asof_date = str(week_start or "").strip() or utc_date_str()
    fact_pack = build_fact_pack_for_assistant(
        artifacts_root=settings.artifacts_root,
        data_version=dv,
        asof_date=asof_date,
        period="weekly",
        web_db_path=(settings.storage_dir / "web.db") if str(settings.runtime_storage_backend or "sqlite") == "sqlite" else None,
    )
    plan = build_weekly_plan_from_fact_pack(
        fact_pack=fact_pack,
        question=str(question or "Сформируй план на неделю"),
        week_start=str(week_start or "").strip() or None,
        farm_id=(str(farm_id).strip() if farm_id else None),
        cfg=load_weekly_plan_copilot_config(),
    )
    return plan


@app.post("/weekly_plans/generate")
def weekly_plans_generate_ui(
    request: Request,
    week_start: str = Form(...),
    data_version: str = Form(...),
    farm_id: str = Form(""),
    question: str = Form("Сформируй план на неделю"),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    try:
        plan = _generate_weekly_plan_payload(
            data_version=str(data_version or ""),
            week_start=str(week_start or ""),
            question=str(question or "Сформируй план на неделю"),
            farm_id=(str(farm_id).strip() if farm_id else None),
        )
        plan_id = create_weekly_plan(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            p=WeeklyPlanCreate(
                name=str(plan.get("name") or f"AI-план на неделю {week_start}"),
                week_start=str(plan.get("week_start") or week_start),
                summary=str(plan.get("summary") or ""),
                farm_id=(str(plan.get("farm_id")) if plan.get("farm_id") else None),
                data_version=str(plan.get("data_version") or data_version),
                action_items=list(plan.get("action_items") or []),
            ),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.generate",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        run_id=_best_run_id((list(plan.get("source_run_ids") or [None])[0])),
        after={
            "plan": after,
            "generator": plan.get("generator"),
            "question": plan.get("question"),
            "source_run_ids": list(plan.get("source_run_ids") or []),
            "source_sections": list(plan.get("source_sections") or []),
            "item_count": len(list(plan.get("action_items") or [])),
            "via": "ui",
        },
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=generated", status_code=303)


@app.post("/weekly_plans/create")
def weekly_plans_create(
    request: Request,
    week_start: str = Form(...),
    name: str = Form(...),
    summary: str = Form(""),
    farm_id: str = Form(""),
    data_version: str = Form(""),
    actions: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    p = WeeklyPlanCreate(
        name=str(name or ""),
        week_start=str(week_start or ""),
        summary=(str(summary).strip() if summary else None),
        farm_id=(str(farm_id).strip() if farm_id else None),
        data_version=(str(data_version).strip() if data_version else None),
        action_items=_parse_actions_lines(actions),
    )
    try:
        plan_id = create_weekly_plan(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            p=p,
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans?error={str(e)[:200]}", status_code=303)

    ip, ua = _get_ip_ua(request)
    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.create",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=created", status_code=303)


@app.get("/weekly_plans/{plan_id}", response_class=HTMLResponse)
def weekly_plan_detail_page(plan_id: str, request: Request, user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_VIEW)), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    p = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not p:
        raise HTTPException(404)
    error = (request.query_params.get("error") or "").strip() or None
    notice = (request.query_params.get("notice") or "").strip() or None

    tasks_map = get_weekly_plan_tasks_map(conn, tenant_id=tenant_id, plan_id=plan_id)
    pdf_rel_path = None
    pdf_exists = False
    try:
        pdf_rel_path = str((p.get("pdf_rel_path") or get_weekly_plan_pdf_rel_path(plan=p)))
        pdf_full_path = (settings.artifacts_root / Path(pdf_rel_path).relative_to("artifacts")) if pdf_rel_path.startswith("artifacts/") else (settings.artifacts_root / pdf_rel_path)
        pdf_exists = pdf_full_path.exists()
    except Exception:
        pdf_rel_path = None
        pdf_exists = False

    perms = set(user.get("permissions") or [])
    can_write = (rbac.PERM_WEEKLY_PLANS_WRITE in perms)
    can_approve = (rbac.PERM_WEEKLY_PLANS_APPROVE in perms)
    can_archive = (rbac.PERM_WEEKLY_PLANS_ARCHIVE in perms)
    return _render(
        request,
        "weekly_plan_detail.html",
        user=user,
        plan=p,
        tasks_map=tasks_map,
        can_write=can_write,
        can_approve=can_approve,
        can_archive=can_archive,
        pdf_rel_path=pdf_rel_path,
        pdf_exists=pdf_exists,
        error=error,
        notice=notice,
        active="weekly_plans",
    )


@app.post("/weekly_plans/{plan_id}/update")
def weekly_plan_update_ui(
    plan_id: str,
    request: Request,
    week_start: str = Form(""),
    name: str = Form(""),
    summary: str = Form(""),
    farm_id: str = Form(""),
    data_version: str = Form(""),
    actions: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        update_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            name=(str(name) if name is not None else None),
            summary=(str(summary) if summary is not None else None),
            farm_id=(str(farm_id) if farm_id is not None else None),
            data_version=(str(data_version) if data_version is not None else None),
            week_start=(str(week_start) if week_start is not None else None),
            action_items=_parse_actions_lines(actions),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans/{plan_id}?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.update",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=saved", status_code=303)


@app.post("/weekly_plans/{plan_id}/request_approval")
def weekly_plan_request_approval_ui(
    plan_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        res = request_approval_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            requested_by=int(user.get("id", 0)),
            requested_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans/{plan_id}?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.request_approval",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"plan": after, "request": res, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=approval_requested", status_code=303)


@app.post("/weekly_plans/{plan_id}/export_pdf")
def weekly_plan_export_pdf_ui(
    plan_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        rep = export_weekly_plan_pdf(
            conn,
            artifacts_root=settings.artifacts_root,
            tenant_id=tenant_id,
            plan_id=plan_id,
            exported_by=int(user.get("id", 0)),
            exported_by_username=str(user.get("username", "")),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans/{plan_id}?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.export_pdf",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"plan": after, "pdf_rel_path": rep.get("pdf_rel_path"), "meta_path": rep.get("meta_path"), "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=pdf_exported", status_code=303)


@app.post("/weekly_plans/{plan_id}/approve")
def weekly_plan_approve_ui(
    plan_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        res = approve_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            approved_by=int(user.get("id", 0)),
            approved_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans/{plan_id}?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.approve",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        run_id=_best_run_id((res or {}).get("tasks_run_id")),
        before=before,
        after={"plan": after, "tasks": {"created": (res.get("tasks_created") or [])[:20], "reused": (res.get("tasks_reused") or [])[:20], "tasks_run_id": res.get("tasks_run_id")}, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    created_n = len(res.get("tasks_created") or [])
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=approved_created_{created_n}_tasks", status_code=303)


@app.post("/weekly_plans/{plan_id}/reject")
def weekly_plan_reject_ui(
    plan_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        reject_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            rejected_by=int(user.get("id", 0)),
            rejected_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans/{plan_id}?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.reject",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"plan": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=rejected", status_code=303)


@app.post("/weekly_plans/{plan_id}/archive")
def weekly_plan_archive_ui(
    plan_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WEEKLY_PLANS_ARCHIVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise HTTPException(404)
    try:
        archive_weekly_plan(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            archived_by=int(user.get("id", 0)),
            archived_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/weekly_plans/{plan_id}?error={str(e)[:200]}", status_code=303)

    after = get_weekly_plan(conn, tenant_id=tenant_id, plan_id=plan_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="weekly_plan.archive",
        object_type="weekly_plan",
        object_id=str(plan_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"plan": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/weekly_plans/{plan_id}?notice=archived", status_code=303)


# --- T12-04: What-If scenarios UI (approvals: draft -> approved -> archived) ---


def _safe_json_loads(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except Exception as e:
        raise ValueError(f"params_json: невалидный JSON ({str(e)[:120]})")
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise ValueError("params_json: ожидается объект JSON (словарь)")
    return v


@app.get("/whatif_scenarios", response_class=HTMLResponse)
def whatif_scenarios_page(request: Request, user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_VIEW)), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    status = (request.query_params.get("status") or "").strip() or None
    q = (request.query_params.get("q") or "").strip() or None
    error = (request.query_params.get("error") or "").strip() or None
    notice = (request.query_params.get("notice") or "").strip() or None

    try:
        res = list_scenarios(conn, tenant_id=tenant_id, status=status, q=q, limit=200, offset=0)
    except Exception as e:
        res = {"total": 0, "scenarios": []}
        error = error or str(e)

    filters = SimpleNamespace(status=status or "", q=q or "")
    perms = set(user.get("permissions") or [])
    can_write = (rbac.PERM_WHATIF_SCENARIOS_WRITE in perms)
    return _render(
        request,
        "whatif_scenarios.html",
        user=user,
        scenarios=list(res.get("scenarios") or []),
        total=int(res.get("total") or 0),
        filters=filters,
        can_write=can_write,
        error=error,
        notice=notice,
        active="whatif_scenarios",
    )


@app.post("/whatif_scenarios/create")
def whatif_scenario_create_ui(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    data_version: str = Form(""),
    params_json: str = Form("{}"),
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    try:
        params = _safe_json_loads(params_json)
        scenario_id = create_scenario(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            s=WhatIfScenarioCreate(
                name=str(name or ""),
                description=(str(description).strip() if description else None),
                data_version=(str(data_version).strip() if data_version else None),
                params=params,
            ),
        )
    except Exception as e:
        return RedirectResponse(url=f"/whatif_scenarios?error={str(e)[:200]}", status_code=303)

    ip, ua = _get_ip_ua(request)
    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.create",
        object_type="whatif_scenario",
        object_id=str(scenario_id),
        data_version=(after or {}).get("data_version"),
        after={"scenario": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?notice=created", status_code=303)


@app.get("/whatif_scenarios/{scenario_id}", response_class=HTMLResponse)
def whatif_scenario_detail_page(
    scenario_id: str,
    request: Request,
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_VIEW)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    s = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not s:
        raise HTTPException(404)

    error = (request.query_params.get("error") or "").strip() or None
    notice = (request.query_params.get("notice") or "").strip() or None

    perms = set(user.get("permissions") or [])
    can_write = (rbac.PERM_WHATIF_SCENARIOS_WRITE in perms) and (str(s.get("status")) == "draft")
    can_approve = (rbac.PERM_WHATIF_SCENARIOS_APPROVE in perms) and (str(s.get("status")) != "archived")
    can_archive = (rbac.PERM_WHATIF_SCENARIOS_ARCHIVE in perms) and (str(s.get("status")) != "archived")
    can_clone = (rbac.PERM_WHATIF_SCENARIOS_CLONE in perms)

    params_json = json.dumps(s.get("params") or {}, ensure_ascii=False, indent=2)
    return _render(
        request,
        "whatif_scenario_detail.html",
        user=user,
        scenario=s,
        params_json=params_json,
        can_write=can_write,
        can_approve=can_approve,
        can_archive=can_archive,
        can_clone=can_clone,
        error=error,
        notice=notice,
        active="whatif_scenarios",
    )


@app.post("/whatif_scenarios/{scenario_id}/update")
def whatif_scenario_update_ui(
    scenario_id: str,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    data_version: str = Form(""),
    params_json: str = Form("{}"),
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_WRITE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)

    try:
        params = _safe_json_loads(params_json)
        update_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            name=(str(name) if name is not None else None),
            description=(str(description) if description is not None else None),
            data_version=(str(data_version) if data_version is not None else None),
            params=params,
        )
    except Exception as e:
        return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?error={str(e)[:200]}", status_code=303)

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.update",
        object_type="whatif_scenario",
        object_id=str(scenario_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"scenario": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?notice=saved", status_code=303)


@app.post("/whatif_scenarios/{scenario_id}/approve")
def whatif_scenario_approve_ui(
    scenario_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    try:
        approve_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            approved_by=int(user.get("id", 0)),
            approved_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?error={str(e)[:200]}", status_code=303)

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.approve",
        object_type="whatif_scenario",
        object_id=str(scenario_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"scenario": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?notice=approved", status_code=303)


@app.post("/whatif_scenarios/{scenario_id}/reject")
def whatif_scenario_reject_ui(
    scenario_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_APPROVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    try:
        reject_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            rejected_by=int(user.get("id", 0)),
            rejected_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?error={str(e)[:200]}", status_code=303)

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.reject",
        object_type="whatif_scenario",
        object_id=str(scenario_id),
        data_version=(after or {}).get("data_version"),
        before=before,
        after={"scenario": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?notice=rejected", status_code=303)


@app.post("/whatif_scenarios/{scenario_id}/archive")
def whatif_scenario_archive_ui(
    scenario_id: str,
    request: Request,
    comment: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_ARCHIVE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    try:
        archive_scenario(
            conn,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            archived_by=int(user.get("id", 0)),
            archived_by_username=str(user.get("username", "")),
            comment=(str(comment).strip() if comment else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?error={str(e)[:200]}", status_code=303)

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.archive",
        object_type="whatif_scenario",
        object_id=str(scenario_id),
        data_version=(after or {}).get("data_version"),
        run_id=_scenario_run_id(after),
        before=before,
        after={"scenario": after, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?notice=archived", status_code=303)


@app.post("/whatif_scenarios/{scenario_id}/clone")
def whatif_scenario_clone_ui(
    scenario_id: str,
    request: Request,
    name: str = Form(""),
    user=Depends(require_permissions(rbac.PERM_WHATIF_SCENARIOS_CLONE)),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    before = get_scenario(conn, tenant_id=tenant_id, scenario_id=scenario_id)
    if not before:
        raise HTTPException(404)
    try:
        new_id = clone_scenario(
            conn,
            tenant_id=tenant_id,
            source_scenario_id=scenario_id,
            user_id=int(user.get("id", 0)),
            username=str(user.get("username", "")),
            name=(str(name).strip() if name else None),
        )
    except Exception as e:
        return RedirectResponse(url=f"/whatif_scenarios/{scenario_id}?error={str(e)[:200]}", status_code=303)

    after = get_scenario(conn, tenant_id=tenant_id, scenario_id=new_id)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="whatif_scenario.clone",
        object_type="whatif_scenario",
        object_id=str(new_id),
        data_version=(after or {}).get("data_version"),
        run_id=_scenario_run_id(after),
        before=before,
        after={"scenario": after, "cloned_from": scenario_id, "via": "ui"},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url=f"/whatif_scenarios/{new_id}?notice=cloned", status_code=303)

@app.get("/api/admin/permission-matrix")
def api_admin_permission_matrix(
    user=Depends(require_permissions(rbac.PERM_USERS_MANAGE)),
    conn=Depends(get_db),
):
    roles = list_roles(conn)
    role_permissions = {role: get_permissions_for_role(conn, role) for role in roles}
    try:
        cfg = load_permission_matrix(settings.project_root)
    except SecurityMatrixConfigError as exc:
        raise HTTPException(status_code=500, detail={"error": "permission_matrix_invalid", "detail": str(exc)})
    return build_permission_matrix_view(matrix_cfg=cfg, role_permissions=role_permissions)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, user=Depends(require_permissions(rbac.PERM_USERS_MANAGE)), conn=Depends(get_db)):
    tenant_id = str(user.get("tenant_id") or "default")
    users = list_users_v2(conn, tenant_id=tenant_id, only_active=False, limit=500)
    roles = list_roles(conn)
    role_permissions = {role: get_permissions_for_role(conn, role) for role in roles}
    matrix = None
    matrix_error = None
    try:
        cfg = load_permission_matrix(settings.project_root)
        matrix = build_permission_matrix_view(matrix_cfg=cfg, role_permissions=role_permissions)
    except SecurityMatrixConfigError as exc:
        matrix_error = str(exc)
    return _render(
        request,
        "admin_users.html",
        active="admin_users",
        user=user,
        title="Security / Users",
        users=users,
        roles=roles,
        role_permissions=role_permissions,
        matrix=matrix,
        matrix_error=matrix_error,
        flash_message=request.query_params.get("msg"),
        flash_level=request.query_params.get("level", "ok"),
    )


@app.post("/admin/users/create")
def admin_users_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user=Depends(require_permissions(rbac.PERM_USERS_MANAGE)),
    conn=Depends(get_db),
):
    tenant_id = str(user.get("tenant_id") or "default")
    username_v = _validate_admin_username(username)
    password_v = _validate_admin_password(password)
    roles = set(list_roles(conn))
    if role not in roles:
        raise HTTPException(status_code=400, detail={"error": "invalid_role", "detail": f"Неизвестная роль: {role}"})
    if get_user_v2_any_by_username(conn, tenant_id=tenant_id, username=username_v):
        raise HTTPException(status_code=400, detail={"error": "duplicate_username", "detail": f"Пользователь '{username_v}' уже существует"})
    create_user_v2(conn, tenant_id=tenant_id, username=username_v, password_hash=hash_password(password_v), role=role)
    created = get_user_v2_any_by_username(conn, tenant_id=tenant_id, username=username_v) or {}
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id") or 0),
        username=str(user.get("username") or ""),
        role=str(user.get("role") or ""),
        action="security.user.create",
        object_type="user",
        object_id=str(created.get("id") or username_v),
        after={"username": username_v, "role": role, "is_active": 1},
        ip=ip,
        user_agent=ua,
    )
    return _admin_redirect(f"Пользователь '{username_v}' создан")


@app.post("/admin/users/{user_id}/role")
def admin_users_set_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    user=Depends(require_permissions(rbac.PERM_USERS_MANAGE)),
    conn=Depends(get_db),
):
    tenant_id = str(user.get("tenant_id") or "default")
    current = get_user_v2_any_by_id(conn, tenant_id=tenant_id, user_id=user_id)
    if not current:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "detail": f"Пользователь id={user_id} не найден"})
    roles = set(list_roles(conn))
    if role not in roles:
        raise HTTPException(status_code=400, detail={"error": "invalid_role", "detail": f"Неизвестная роль: {role}"})
    if str(current.get("role")) == rbac.ROLE_ADMIN and role != rbac.ROLE_ADMIN and int(current.get("is_active") or 0) == 1:
        if count_active_users_by_role(conn, tenant_id=tenant_id, role=rbac.ROLE_ADMIN) <= 1:
            raise HTTPException(status_code=400, detail={"error": "last_admin", "detail": "Нельзя снять роль Admin у последнего активного администратора"})
    before = {"username": current.get("username"), "role": current.get("role")}
    update_user_v2_role(conn, tenant_id=tenant_id, user_id=user_id, role=role)
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id") or 0),
        username=str(user.get("username") or ""),
        role=str(user.get("role") or ""),
        action="security.user.role_update",
        object_type="user",
        object_id=str(user_id),
        before=before,
        after={"username": current.get("username"), "role": role},
        ip=ip,
        user_agent=ua,
    )
    return _admin_redirect(f"Роль пользователя '{current.get('username')}' обновлена")


@app.post("/admin/users/{user_id}/reset_password")
def admin_users_reset_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
    user=Depends(require_permissions(rbac.PERM_USERS_MANAGE)),
    conn=Depends(get_db),
):
    tenant_id = str(user.get("tenant_id") or "default")
    current = get_user_v2_any_by_id(conn, tenant_id=tenant_id, user_id=user_id)
    if not current:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "detail": f"Пользователь id={user_id} не найден"})
    password_v = _validate_admin_password(password)
    update_user_v2_password_hash(conn, tenant_id=tenant_id, user_id=user_id, password_hash=hash_password(password_v))
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id") or 0),
        username=str(user.get("username") or ""),
        role=str(user.get("role") or ""),
        action="security.user.password_reset",
        object_type="user",
        object_id=str(user_id),
        after={"username": current.get("username"), "password_reset": True},
        ip=ip,
        user_agent=ua,
    )
    return _admin_redirect(f"Пароль пользователя '{current.get('username')}' обновлен")


@app.post("/admin/users/{user_id}/status")
def admin_users_set_status(
    user_id: int,
    request: Request,
    is_active: int = Form(...),
    user=Depends(require_permissions(rbac.PERM_USERS_MANAGE)),
    conn=Depends(get_db),
):
    tenant_id = str(user.get("tenant_id") or "default")
    current = get_user_v2_any_by_id(conn, tenant_id=tenant_id, user_id=user_id)
    if not current:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "detail": f"Пользователь id={user_id} не найден"})
    target_active = 1 if int(is_active or 0) else 0
    if int(current.get("id") or 0) == int(user.get("id") or -1) and target_active == 0:
        raise HTTPException(status_code=400, detail={"error": "self_disable", "detail": "Нельзя деактивировать текущего пользователя из своей сессии"})
    if str(current.get("role")) == rbac.ROLE_ADMIN and int(current.get("is_active") or 0) == 1 and target_active == 0:
        if count_active_users_by_role(conn, tenant_id=tenant_id, role=rbac.ROLE_ADMIN) <= 1:
            raise HTTPException(status_code=400, detail={"error": "last_admin", "detail": "Нельзя деактивировать последнего активного администратора"})
    before = {"username": current.get("username"), "is_active": int(current.get("is_active") or 0)}
    set_user_v2_active(conn, tenant_id=tenant_id, user_id=user_id, is_active=bool(target_active))
    ip, ua = _get_ip_ua(request)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id") or 0),
        username=str(user.get("username") or ""),
        role=str(user.get("role") or ""),
        action="security.user.status_update",
        object_type="user",
        object_id=str(user_id),
        before=before,
        after={"username": current.get("username"), "is_active": target_active},
        ip=ip,
        user_agent=ua,
    )
    label = "активирован" if target_active else "деактивирован"
    return _admin_redirect(f"Пользователь '{current.get('username')}' {label}")


@app.get("/configs", response_class=HTMLResponse)
def configs_page(request: Request, user=Depends(require_permissions("configs.manage")), conn=Depends(get_db)):
    # list override files
    files = []
    base = settings.configs_dir
    for p in sorted(base.rglob("*")):
        if p.is_file():
            files.append(str(p.relative_to(base)))
    return _render(request, "configs.html", user=user, files=files)


@app.post("/configs/upload")
def configs_upload(
    request: Request,
    target_rel_path: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(require_permissions("configs.manage")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    rel = (target_rel_path or "").lstrip("/")
    # store under web_storage/config_overrides/<rel>
    dest = safe_join(settings.configs_dir, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        written = save_upload_limited(file.file, dest=dest, max_bytes=settings.max_mapping_bytes)
    except ValueError as e:
        if str(e) == "upload_too_large":
            raise HTTPException(
                status_code=413,
                detail=f"Конфиг слишком большой. Лимит: {settings.max_mapping_bytes // (1024*1024)} MB",
            )
        raise

    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get("id", 0)),
        username=user.get("username", ""),
        role=user.get("role", ""),
        action="configs.upload",
        object_type="config",
        object_id=rel,
        after={"size": int(written)},
        ip=ip,
        user_agent=ua,
        status="OK",
    )
    return RedirectResponse(url="/configs", status_code=302)


def _audit_filters_from_request(request: Request) -> dict[str, Optional[str] | int]:
    qp = request.query_params
    raw_limit = qp.get('limit', '200')
    try:
        limit = int(raw_limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={'error': 'invalid_audit_limit', 'detail': f'limit должен быть целым числом, получено: {raw_limit!r}'}) from exc
    if not (1 <= limit <= 5000):
        raise HTTPException(status_code=400, detail={'error': 'invalid_audit_limit', 'detail': f'limit должен быть в диапазоне 1..5000, получено: {limit}'})
    raw_scope = (qp.get('scope') or 'active').strip() or 'active'
    try:
        scope = validate_audit_scope(raw_scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'error': 'invalid_audit_scope', 'detail': str(exc)}) from exc
    filters: dict[str, Optional[str] | int] = {
        'action': (qp.get('action') or '').strip() or None,
        'action_prefix': (qp.get('action_prefix') or '').strip() or None,
        'action_group': (qp.get('action_group') or '').strip() or None,
        'status': (qp.get('status') or '').strip() or None,
        'username': (qp.get('username') or '').strip() or None,
        'role': (qp.get('role') or '').strip() or None,
        'object_type': (qp.get('object_type') or '').strip() or None,
        'object_id': (qp.get('object_id') or '').strip() or None,
        'object_ref': (qp.get('object_ref') or '').strip() or None,
        'run_id': (qp.get('run_id') or '').strip() or None,
        'data_version': (qp.get('data_version') or '').strip() or None,
        'request_id': (qp.get('request_id') or '').strip() or None,
        'q': (qp.get('q') or '').strip() or None,
        'ts_from': (qp.get('ts_from') or '').strip() or None,
        'ts_to': (qp.get('ts_to') or '').strip() or None,
        'scope': scope,
        'limit': limit,
    }
    return filters


def _load_audit_retention_or_500() -> dict:
    try:
        return load_audit_retention_config(settings.project_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail={'error': 'invalid_audit_retention_config', 'detail': str(exc)}) from exc


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, user=Depends(require_permissions("audit.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    filters = _audit_filters_from_request(request)
    rows = list_audit(conn, tenant_id=tenant_id, offset=0, **filters)
    retention_cfg = _load_audit_retention_or_500()
    facets = aggregate_audit_facets(
        conn,
        tenant_id=tenant_id,
        action=filters.get('action'),
        action_prefix=filters.get('action_prefix'),
        action_group=filters.get('action_group'),
        status=filters.get('status'),
        username=filters.get('username'),
        role=filters.get('role'),
        object_type=filters.get('object_type'),
        object_id=filters.get('object_id'),
        object_ref=filters.get('object_ref'),
        run_id=filters.get('run_id'),
        data_version=filters.get('data_version'),
        request_id=filters.get('request_id'),
        q=filters.get('q'),
        ts_from=filters.get('ts_from'),
        ts_to=filters.get('ts_to'),
        scope=str(filters.get('scope') or 'active'),
        top_actions_limit=int(retention_cfg['facets']['top_actions_limit']),
        top_users_limit=int(retention_cfg['facets']['top_users_limit']),
    )
    retention_cutoff = retention_cutoff_ts(archive_after_days=int(retention_cfg['archive_after_days']))
    archivable_count = count_archivable_audit(conn, tenant_id=tenant_id, older_than_ts=retention_cutoff)
    can_archive = 'configs.manage' in (user.get('permissions') or [])
    return _render(
        request,
        "audit.html",
        user=user,
        rows=rows,
        filters=filters,
        facets=facets,
        retention_cfg=retention_cfg,
        retention_cutoff=retention_cutoff,
        archivable_count=archivable_count,
        can_archive=can_archive,
    )


@app.get("/api/audit")
def api_audit(request: Request, user=Depends(require_permissions("audit.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    filters = _audit_filters_from_request(request)
    rows = list_audit(conn, tenant_id=tenant_id, offset=0, **filters)
    retention_cfg = _load_audit_retention_or_500()
    facets = aggregate_audit_facets(
        conn,
        tenant_id=tenant_id,
        action=filters.get('action'),
        action_prefix=filters.get('action_prefix'),
        action_group=filters.get('action_group'),
        status=filters.get('status'),
        username=filters.get('username'),
        role=filters.get('role'),
        object_type=filters.get('object_type'),
        object_id=filters.get('object_id'),
        object_ref=filters.get('object_ref'),
        run_id=filters.get('run_id'),
        data_version=filters.get('data_version'),
        request_id=filters.get('request_id'),
        q=filters.get('q'),
        ts_from=filters.get('ts_from'),
        ts_to=filters.get('ts_to'),
        scope=str(filters.get('scope') or 'active'),
        top_actions_limit=int(retention_cfg['facets']['top_actions_limit']),
        top_users_limit=int(retention_cfg['facets']['top_users_limit']),
    )
    return {"rows": rows, "filters": filters, "schema_version": 2, "facets": facets}


@app.get("/api/audit/facets")
def api_audit_facets(request: Request, user=Depends(require_permissions("audit.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    filters = _audit_filters_from_request(request)
    retention_cfg = _load_audit_retention_or_500()
    facets = aggregate_audit_facets(
        conn,
        tenant_id=tenant_id,
        action=filters.get('action'),
        action_prefix=filters.get('action_prefix'),
        action_group=filters.get('action_group'),
        status=filters.get('status'),
        username=filters.get('username'),
        role=filters.get('role'),
        object_type=filters.get('object_type'),
        object_id=filters.get('object_id'),
        object_ref=filters.get('object_ref'),
        run_id=filters.get('run_id'),
        data_version=filters.get('data_version'),
        request_id=filters.get('request_id'),
        q=filters.get('q'),
        ts_from=filters.get('ts_from'),
        ts_to=filters.get('ts_to'),
        scope=str(filters.get('scope') or 'active'),
        top_actions_limit=int(retention_cfg['facets']['top_actions_limit']),
        top_users_limit=int(retention_cfg['facets']['top_users_limit']),
    )
    return {"filters": filters, "facets": facets}


@app.post("/api/audit/archive-old")
def api_audit_archive_old(
    request: Request,
    dry_run: int = Form(0),
    limit: str = Form(''),
    user=Depends(require_permissions("audit.view", "configs.manage")),
    conn=Depends(get_db),
):
    tenant_id = user.get("tenant_id", "default")
    retention_cfg = _load_audit_retention_or_500()
    if not retention_cfg.get('enabled', True):
        raise HTTPException(status_code=400, detail={'error': 'audit_retention_disabled', 'detail': 'Архивация audit отключена в configs/security/audit_retention_v1.yaml'})
    max_batch_size = int(retention_cfg['max_archive_batch_size'])
    if str(limit or '').strip():
        try:
            effective_limit = int(limit)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={'error': 'invalid_archive_limit', 'detail': f'limit должен быть целым числом, получено: {limit!r}'}) from exc
    else:
        effective_limit = max_batch_size
    if not (1 <= effective_limit <= max_batch_size):
        raise HTTPException(status_code=400, detail={'error': 'invalid_archive_limit', 'detail': f'limit должен быть в диапазоне 1..{max_batch_size}, получено: {effective_limit}'})
    cutoff_ts = retention_cutoff_ts(archive_after_days=int(retention_cfg['archive_after_days']))
    candidates = count_archivable_audit(conn, tenant_id=tenant_id, older_than_ts=cutoff_ts)
    if int(dry_run or 0):
        return {
            'ok': True,
            'dry_run': True,
            'candidates': candidates,
            'cutoff_ts': cutoff_ts,
            'limit': effective_limit,
            'retention': retention_cfg,
        }
    result = archive_old_audit(conn, tenant_id=tenant_id, older_than_ts=cutoff_ts, limit=effective_limit, reason='retention_policy')
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get('id', 0)),
        username=user.get('username', ''),
        role=user.get('role', ''),
        action='config.audit_retention.apply',
        object_type='audit_archive',
        object_id=result['batch_id'],
        before={'candidates': candidates, 'cutoff_ts': cutoff_ts},
        after=result,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        status='OK',
    )
    return {'ok': True, 'dry_run': False, 'result': result, 'remaining_candidates': count_archivable_audit(conn, tenant_id=tenant_id, older_than_ts=cutoff_ts)}


@app.get("/api/audit/export.csv")
def api_audit_export_csv(request: Request, user=Depends(require_permissions("audit.view")), conn=Depends(get_db)):
    tenant_id = user.get("tenant_id", "default")
    filters = _audit_filters_from_request(request)
    rows = list_audit(conn, tenant_id=tenant_id, offset=0, **filters)

    out = io.StringIO()
    cols = [
        'id', 'ts', 'schema_version', 'action_group', 'action', 'status',
        'user_id', 'username', 'role', 'ip', 'user_agent',
        'object_type', 'object_id', 'object_ref',
        'data_version', 'run_id', 'request_id', 'error',
        'archived_at', 'archive_reason', 'archive_batch_id',
        'before_json', 'after_json',
    ]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k) for k in cols})
    payload = out.getvalue()
    stamp = utc_timestamp_compact()
    filename = f'audit_export_{stamp}.csv'
    return StreamingResponse(
        io.BytesIO(payload.encode('utf-8')),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )

@app.get("/pack", response_class=HTMLResponse)
def pack_page(request: Request, user=Depends(get_current_user)):
    dvs = list_data_versions(settings.artifacts_root)
    dv = request.query_params.get("dv") or (dvs[-1] if dvs else "")
    qc_runs = list_qc_runs(settings.artifacts_root, dv) if dv else []
    models = list_model_versions(settings.artifacts_root, dv) if dv else []
    scorings = list_scoring_runs(settings.artifacts_root, dv) if dv else []
    reports = list_report_versions(settings.artifacts_root, dv) if dv else []
    return _render(
        request,
        "pack.html",
        user=user,
        data_versions=dvs,
        selected_dv=dv,
        qc_runs=qc_runs,
        model_versions=models,
        scoring_runs=scorings,
        report_versions=reports,
    )


@app.post("/pack/run")
def pack_run(
    data_version: str = Form(...),
    qc_run: str = Form(...),
    model_version: str = Form(...),
    scoring_run: str = Form(...),
    report_version: str = Form(...),
    user=Depends(require_permissions("pipeline.run")),
    conn=Depends(get_db),
):
    job_request = build_pack_job_request(
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        report_version=report_version,
        artifacts_root=settings.artifacts_root,
    )
    job_id = enqueue_pipeline_job(
        conn,
        request=job_request,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        username=user["username"],
        logs_dir=settings.logs_dir,
    )
    _audit_pipeline_enqueue(conn, user=user, job_id=job_id, kind=job_request.kind, object_id=job_request.object_id, extra_after=job_request.extra_after)
    return RedirectResponse(url="/tasks", status_code=302)
