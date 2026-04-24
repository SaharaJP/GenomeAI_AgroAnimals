from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from packages.contracts.api_boundary_v1 import (
    AlertItem,
    AlertsListResponse,
    ApiLinkage,
    AssistantResolveTargetRequest,
    AssistantResolveTargetResponse,
    DecisionIntelligenceResponse,
    DecisionIntelligenceSummary,
    DecisionIntelligenceTopAction,
    DecisionItem,
    DecisionsListResponse,
    EconomicsListResponse,
    EconomicsScenarioItem,
    EntityRef,
    FeedbackItem,
    FeedbackListResponse,
    FeedbackMetrics,
    InsightItem,
    InsightsListResponse,
    InsightTransitionRequest,
    PilotPackItem,
    PilotResponse,
    PilotSummary,
    PlannerPlanItem,
    PlannerResponse,
    PlannerSummary,
    ProfileResponse,
    ProfileSummary,
    ReadinessCheck,
    ReadinessResponse,
    ReadinessSummary,
    ReportItem,
    ReportsListResponse,
    SupportResponse,
    SupportSummary,
    WorklistItem,
    WorklistsListResponse,
)
from core.common.time import utc_date_str, utc_timestamp_compact
from core.infra.web_db import get_settings
from core.infra.runtime_storage import resolve_runtime_storage_settings, runtime_storage_diagnostics
from core.infra.runtime_state_storage import runtime_state_storage_diagnostics
from web_cabinet.deploy_guard import DeployConfigError, validate_runtime_config
from core.observability import ensure_request_id
from core.release import load_release_metadata
from core.security import has_any_permission as core_has_any_permission
from core.support_sla_incident import build_support_sla_incident_summary
from core.workflow import list_alerts, list_decisions, list_tasks
from core.workflow.alerts import list_alerts_for_object
from core.workflow.decisions import list_decisions_for_object
from core.workflow.summaries import operational_summary_use_case, overdue_tasks_use_case
from core.workflow.tasks import list_tasks_for_object
from genomeai.ai_assistant_rag import build_fact_pack_for_assistant, load_copilot_answer_config
from genomeai.copilot_target_resolver import (
    build_copilot_api_target,
    build_copilot_detail_actions,
    build_copilot_navigation_hints,
    parse_copilot_target,
    resolve_copilot_target_from_fact_pack,
    summarize_target_resolution,
)
from genomeai.copilot_tools import load_copilot_tools_config, resolve_section_required_permission

from .auth import get_current_user, get_db
from .feedback_v1 import compute_feedback_metrics, list_feedback
from .insights_v1 import (
    get_insight as _get_insight,
    list_insights as _list_insights,
    transition_insight as _transition_insight,
)
from .observability import snapshot as obs_snapshot
from .rbac import require_permissions
from .reports_approvals_v1 import list_report_statuses
from .utils import list_data_versions, list_report_versions
from .weekly_plans_v1 import list_pending_approval_weekly_plans, list_weekly_plans, summarize_weekly_plan
from .whatif_reports_v1 import list_reports as list_whatif_reports
from .whatif_scenarios_v1 import list_scenarios

router = APIRouter(prefix='/api/app/v1', tags=['app-boundary-v1'])
def _runtime_settings():
    return get_settings()


def _runtime_release_metadata():
    settings = _runtime_settings()
    return load_release_metadata(project_root=settings.project_root)


def _user_has_any(user: dict[str, Any], *permissions: str) -> bool:
    perms = user.get('permissions') or []
    return core_has_any_permission(perms, *permissions)


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except Exception:
        return None


def _linkage(row: dict[str, Any], *, request: Optional[Request] = None) -> ApiLinkage:
    request_id = None
    if request is not None:
        request_id = getattr(getattr(request, 'state', None), 'request_id', None) or ensure_request_id(request.headers.get('x-request-id'), prefix='req')
    return ApiLinkage(
        data_version=_coerce_str(row.get('data_version')),
        qc_run=_coerce_str(row.get('qc_run')),
        model_version=_coerce_str(row.get('model_version')),
        scoring_run=_coerce_str(row.get('scoring_run')),
        report_version=_coerce_str(row.get('report_version')),
        request_id=_coerce_str(request_id),
    )


def _entity_ref(row: dict[str, Any], *, fallback_label: Optional[str] = None) -> Optional[EntityRef]:
    object_type = _coerce_str(row.get('object_type'))
    object_id = _coerce_str(row.get('object_id'))
    if not object_type or not object_id:
        return None
    return EntityRef(
        object_type=object_type,
        object_id=object_id,
        farm_id=_coerce_str(row.get('farm_id')),
        group_id=_coerce_str(row.get('group_id')),
        label=fallback_label,
    )


def _map_alert(row: dict[str, Any], *, request: Optional[Request] = None) -> AlertItem:
    entity = _entity_ref(row) or EntityRef(
        object_type=_coerce_str(row.get('object_type')) or 'unknown',
        object_id=_coerce_str(row.get('object_id')) or 'unknown',
    )
    return AlertItem(
        alert_id=str(row.get('alert_id') or ''),
        status=str(row.get('status') or 'new'),
        alert_type=str(row.get('alert_type') or ''),
        title=str(row.get('title') or row.get('message') or ''),
        source=_coerce_str(row.get('source')),
        cause=_coerce_str(row.get('cause') or row.get('message')),
        confidence=_coerce_float(row.get('confidence')),
        severity=_coerce_str(row.get('severity')),
        owner_user_id=_coerce_int(row.get('owner_user_id')),
        owner_username=_coerce_str(row.get('owner_username')),
        deadline=_coerce_str(row.get('deadline')),
        entity=entity,
        linkage=_linkage(row, request=request),
        why=dict(row.get('why') or {}),
        what_to_do=list(row.get('what_to_do') or []),
        attachments=list(row.get('attachments') or []),
        created_at=_coerce_str(row.get('created_at')),
        updated_at=_coerce_str(row.get('updated_at')),
    )


def _map_worklist(row: dict[str, Any], *, request: Optional[Request] = None) -> WorklistItem:
    entity = _entity_ref(row)
    return WorklistItem(
        task_id=str(row.get('task_id') or ''),
        status=str(row.get('status') or 'open'),
        task_type=str(row.get('task_type') or ''),
        title=str(row.get('title') or ''),
        domain=_coerce_str(row.get('domain')),
        priority=int(row.get('priority') or 3),
        due_at=_coerce_str(row.get('due_at')),
        stage=_coerce_str(row.get('stage')),
        assignee_team=_coerce_str(row.get('assignee_team')),
        owner_user_id=_coerce_int(row.get('owner_user_id')),
        owner_username=_coerce_str(row.get('owner_username')),
        related_alert=_coerce_str(row.get('related_alert')),
        worklist_type=_coerce_str(row.get('worklist_type')),
        confidence=_coerce_float(row.get('confidence')),
        entity=entity,
        linkage=_linkage(row, request=request),
        why=dict(row.get('why') or {}),
        what_to_do=list(row.get('what_to_do') or []),
        attachments=list(row.get('attachments') or []),
        created_at=_coerce_str(row.get('created_at')),
        updated_at=_coerce_str(row.get('updated_at')),
        is_overdue=bool(row.get('is_overdue')) if row.get('is_overdue') is not None else None,
    )




def _map_decision(row: dict[str, Any], *, request: Optional[Request] = None) -> DecisionItem:
    raw = dict(row or {})

    def _s(value: Any) -> str | None:
        try:
            return _coerce_str(value)
        except Exception:
            if value is None:
                return None
            return str(value).strip() or None

    def _n(value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except Exception:
            return None

    def _safe_url(*route_names: str, **params: Any) -> str | None:
        if request is None:
            return None
        for route_name in route_names:
            try:
                return str(request.url_for(route_name, **params))
            except Exception:
                continue
        return None

    fields = getattr(DecisionItem, "model_fields", {}) or {}
    kwargs: dict[str, Any] = {}

    decision_id = _s(raw.get("decision_id")) or _s(raw.get("id")) or ""

    def put(name: str, value: Any) -> None:
        if name in fields and value is not None:
            kwargs[name] = value

    put("decision_id", decision_id)
    put("id", decision_id)

    action = _s(raw.get("action")) or "decision"
    reason = _s(raw.get("reason"))
    comment = _s(raw.get("comment"))
    created_at = _s(raw.get("created_at")) or ""
    updated_at = _s(raw.get("updated_at"))
    object_type = _s(raw.get("object_type"))
    object_id = _s(raw.get("object_id"))
    related_alert = _s(raw.get("related_alert"))
    farm_id = _s(raw.get("farm_id"))
    group_id = _s(raw.get("group_id"))
    site_id = _s(raw.get("site_id"))
    data_version = _s(raw.get("data_version"))
    report_version = _s(raw.get("report_version"))
    scoring_run = _s(raw.get("scoring_run"))
    run_id = _s(raw.get("run_id"))
    username = _s(raw.get("username"))
    role = _s(raw.get("role"))
    user_id = _n(raw.get("user_id"))

    put("action", action)
    put("title", action)
    put("reason", reason)
    put("comment", comment)
    put("created_at", created_at)
    put("updated_at", updated_at)
    put("object_type", object_type)
    put("object_id", object_id)
    put("related_alert", related_alert)
    put("farm_id", farm_id)
    put("group_id", group_id)
    put("site_id", site_id)
    put("data_version", data_version)
    put("report_version", report_version)
    put("scoring_run", scoring_run)
    put("run_id", run_id)
    put("username", username)
    put("role", role)
    put("user_id", user_id)

    if "entity" in fields:
        kwargs["entity"] = {
            "object_type": object_type,
            "object_id": object_id,
            "farm_id": farm_id,
            "group_id": group_id,
            "label": object_id,
        }

    if "linkage" in fields:
        kwargs["linkage"] = {
            "data_version": data_version,
            "report_version": report_version,
            "scoring_run": scoring_run,
            "run_id": run_id,
            "related_alert": related_alert,
        }

    if "links" in fields:
        self_url = _safe_url(
            "api_decision_log_v2_get",
            "boundary_decision_get",
            "boundary_decisions_get",
            decision_id=decision_id,
        )
        kwargs["links"] = {
            "self": self_url,
        }

    if "status" in fields and "status" not in kwargs:
        kwargs["status"] = _s(raw.get("status")) or "recorded"

    if "summary" in fields and "summary" not in kwargs:
        kwargs["summary"] = comment or reason or action

    try:
        return DecisionItem(**kwargs)
    except Exception:
        for name, meta in fields.items():
            if name in kwargs:
                continue
            try:
                required = bool(meta.is_required())
            except Exception:
                required = False
            if not required:
                continue

            ann = str(getattr(meta, "annotation", "") or "").lower()

            if name in {"decision_id", "id"}:
                kwargs[name] = decision_id or "decision"
            elif "list" in ann:
                kwargs[name] = []
            elif "dict" in ann or "mapping" in ann:
                kwargs[name] = {}
            elif "bool" in ann:
                kwargs[name] = False
            elif "int" in ann:
                kwargs[name] = 0
            elif "float" in ann or "decimal" in ann:
                kwargs[name] = 0.0
            else:
                kwargs[name] = ""

        return DecisionItem(**kwargs)

def _map_feedback(row: dict[str, Any], *, request: Optional[Request] = None) -> FeedbackItem:
    return FeedbackItem(
        feedback_id=str(row.get('feedback_id') or ''),
        created_at=str(row.get('created_at') or ''),
        decision=str(row.get('decision') or ''),
        reason_code=str(row.get('reason_code') or ''),
        comment=_coerce_str(row.get('comment')),
        recommendation_id=_coerce_str(row.get('recommendation_id')),
        related_alert=_coerce_str(row.get('related_alert')),
        task_id=_coerce_str(row.get('task_id')),
        entity=_entity_ref(row),
        linkage=_linkage(row, request=request),
        feedback_source=_coerce_str(row.get('feedback_source')),
        metadata=dict(row.get('metadata') or {}),
    )


def _iter_pilot_pack_dirs(artifacts_root: Path) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for data_version in list_data_versions(artifacts_root):
        packs_dir = artifacts_root / data_version / 'pilot_packs'
        if not packs_dir.exists():
            continue
        for pack_dir in sorted([p for p in packs_dir.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True):
            items.append((str(data_version), pack_dir))
    return items


def _build_readiness_checks(*, settings) -> tuple[str, list[ReadinessCheck], dict[str, Any]]:
    checks: list[ReadinessCheck] = []
    runtime_storage = runtime_storage_diagnostics(
        resolve_runtime_storage_settings(
            project_root=settings.project_root,
            storage_dir=settings.storage_dir,
            sqlite_db_path=getattr(settings, 'db_path', settings.storage_dir / 'web.db'),
        )
    ).as_dict()
    source_paths = {
        'project_root': str(settings.project_root),
        'storage_dir': str(settings.storage_dir),
        'artifacts_root': str(settings.artifacts_root),
        'runtime_storage': runtime_storage,
        'runtime_state': runtime_state_storage_diagnostics().as_dict(),
    }
    try:
        cfg = validate_runtime_config(settings=settings)
        profile = str(cfg.get('profile') or 'dev')
        storage_cfg = dict((cfg.get('runtime_storage') or {}))
        checks.append(ReadinessCheck(check_id='runtime_config', status='pass', severity='info', message='Runtime config validated'))
        checks.append(ReadinessCheck(check_id='permission_matrix', status='pass', severity='info', message=f"Permission matrix version={cfg.get('permission_matrix_version')}"))
        checks.append(ReadinessCheck(check_id='runtime_storage_backend', status='pass', severity='info', message=f"backend={storage_cfg.get('backend')} migration_status={storage_cfg.get('migration_status')}"))
        checks.append(ReadinessCheck(check_id='openai_secret', status='pass' if cfg.get('openai_enabled') else 'warn', severity='info' if cfg.get('openai_enabled') else 'warn', message='OPENAI_API_KEY configured' if cfg.get('openai_enabled') else 'OPENAI_API_KEY not configured'))
        return profile, checks, source_paths
    except DeployConfigError as exc:
        checks.append(ReadinessCheck(check_id='runtime_config', status='fail', severity='error', message=str(exc)))
        checks.append(ReadinessCheck(check_id='runtime_storage_backend', status='fail' if runtime_storage.get('forbidden_fallback_detected') else 'warn', severity='error' if runtime_storage.get('forbidden_fallback_detected') else 'warn', message=f"backend={runtime_storage.get('backend')} migration_status={runtime_storage.get('migration_status')}"))
        profile = str(getattr(settings, 'deploy_profile', None) or 'unknown')
        return profile, checks, source_paths


def _readiness_summary(checks: list[ReadinessCheck]) -> ReadinessSummary:
    passed = sum(1 for item in checks if item.status == 'pass')
    warnings = sum(1 for item in checks if item.status == 'warn')
    failed = sum(1 for item in checks if item.status == 'fail')
    overall = 'fail' if failed else ('warn' if warnings else 'pass')
    return ReadinessSummary(overall_status=overall, checks_total=len(checks), passed=passed, warnings=warnings, failed=failed)


@router.get('/alerts', response_model=AlertsListResponse)
def boundary_alerts(
    request: Request,
    status: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(require_permissions('alerts.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    payload = list_alerts(
        conn,
        tenant_id=tenant_id,
        status=status,
        object_type=object_type,
        object_id=object_id,
        limit=int(limit),
        offset=int(offset),
    )
    items = [_map_alert(dict(row), request=request) for row in list(payload.get('alerts') or [])]
    return AlertsListResponse(total=int(payload.get('total') or 0), limit=int(limit), offset=int(offset), items=items)


@router.get('/worklists', response_model=WorklistsListResponse)
def boundary_worklists(
    request: Request,
    status: Optional[str] = None,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(require_permissions('tasks.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    payload = list_tasks(
        conn,
        tenant_id=tenant_id,
        status=status,
        domain=domain,
        assignee_team=assignee_team,
        object_type=object_type,
        object_id=object_id,
        limit=int(limit),
        offset=int(offset),
    )
    items = [_map_worklist(dict(row), request=request) for row in list(payload.get('tasks') or [])]
    return WorklistsListResponse(total=int(payload.get('total') or 0), limit=int(limit), offset=int(offset), items=items)


@router.get('/planner', response_model=PlannerResponse)
def boundary_planner(
    request: Request,
    status: Optional[str] = None,
    limit: int = 20,
    user=Depends(require_permissions('tasks.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    operational = operational_summary_use_case(conn=conn, tenant_id=tenant_id, recent_tasks_limit=int(limit))
    pending = list_pending_approval_weekly_plans(conn, tenant_id=tenant_id, limit=int(limit), offset=0)
    plans = list_weekly_plans(conn, tenant_id=tenant_id, status=status, limit=int(limit), offset=0)
    overdue = overdue_tasks_use_case(conn=conn, tenant_id=tenant_id, limit=int(limit))
    weekly_items = []
    for row in list(plans.get('items') or plans.get('weekly_plans') or []):
        summary = summarize_weekly_plan(dict(row))
        weekly_items.append(
            PlannerPlanItem(
                plan_id=str(summary.get('plan_id') or ''),
                status=str(summary.get('status') or ''),
                name=str(summary.get('name') or ''),
                week_start=str(summary.get('week_start') or ''),
                item_count=int(summary.get('item_count') or 0),
                citation_count=int(summary.get('citation_count') or 0),
                farm_id=_coerce_str(summary.get('farm_id')),
                linkage=ApiLinkage(
                    data_version=_coerce_str(summary.get('data_version')),
                    request_id=_coerce_str(getattr(request.state, 'request_id', None)),
                ),
                approval_requested_at=_coerce_str(summary.get('approval_requested_at')),
                approval_requested_by_username=_coerce_str(summary.get('approval_requested_by_username')),
                approved_at=_coerce_str(summary.get('approved_at')),
                approved_by_username=_coerce_str(summary.get('approved_by_username')),
            )
        )
    overdue_items = [_map_worklist(dict(row), request=request) for row in list(overdue.get('items') or [])]
    summary = PlannerSummary(
        alerts_new=int(((operational.get('alerts') or {}).get('new') or 0)),
        alerts_acknowledged=int(((operational.get('alerts') or {}).get('acknowledged') or 0)),
        alerts_resolved=int(((operational.get('alerts') or {}).get('resolved') or 0)),
        tasks_open=int(((operational.get('tasks') or {}).get('open') or 0)),
        tasks_done=int(((operational.get('tasks') or {}).get('done') or 0)),
        overdue_active=int(overdue.get('count') or 0),
    )
    return PlannerResponse(
        summary=summary,
        pending_approvals=int(pending.get('total') or 0),
        weekly_plans=weekly_items,
        overdue_items=overdue_items,
    )


@router.get('/profiles/{object_type}/{object_id}', response_model=ProfileResponse)
def boundary_profile(
    object_type: str,
    object_id: str,
    request: Request,
    limit: int = 20,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    if not _user_has_any(user, 'alerts.view', 'tasks.view', 'decisionlog.view'):
        raise HTTPException(status_code=403)
    tenant_id = user.get('tenant_id', 'default')
    alerts_payload = list_alerts_for_object(conn, tenant_id=tenant_id, object_type=object_type, object_id=object_id, limit=int(limit), offset=0)
    tasks_payload = list_tasks_for_object(conn, tenant_id=tenant_id, object_type=object_type, object_id=object_id, limit=int(limit), offset=0)
    decisions_payload = list_decisions_for_object(conn, tenant_id=tenant_id, object_type=object_type, object_id=object_id, limit=int(limit), offset=0)
    alerts = [_map_alert(dict(row), request=request) for row in list(alerts_payload.get('alerts') or [])]
    worklists = [_map_worklist(dict(row), request=request) for row in list(tasks_payload.get('tasks') or [])]
    decisions = [_map_decision(dict(row), request=request) for row in list(decisions_payload.get('decisions') or [])]
    alerts_open = sum(1 for item in alerts if item.status in {'new', 'acknowledged'})
    worklists_open = sum(1 for item in worklists if item.status in {'open', 'in_progress'})
    return ProfileResponse(
        entity=EntityRef(object_type=object_type, object_id=object_id),
        summary=ProfileSummary(alerts_open=alerts_open, worklists_open=worklists_open, decisions_total=len(decisions)),
        alerts=alerts,
        worklists=worklists,
        decisions=decisions,
    )


@router.get('/reports', response_model=ReportsListResponse)
def boundary_reports(
    request: Request,
    data_version: Optional[str] = None,
    user=Depends(require_permissions('reports.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    settings = _runtime_settings()
    data_versions = [data_version] if data_version else list_data_versions(settings.artifacts_root)
    items: list[ReportItem] = []
    for dv in data_versions:
        if not dv:
            continue
        versions = list_report_versions(settings.artifacts_root, dv)
        statuses = list_report_statuses(conn, tenant_id=tenant_id, data_version=dv, report_versions=versions)
        for rv in versions:
            status_row = dict(statuses.get(rv) or {})
            items.append(
                ReportItem(
                    data_version=str(dv),
                    report_version=str(rv),
                    status=str(status_row.get('status') or 'draft'),
                    approved_at=_coerce_str(status_row.get('approved_at')),
                    approved_by_username=_coerce_str(status_row.get('approved_by_username')),
                    comment=_coerce_str(status_row.get('comment')),
                    linkage=ApiLinkage(data_version=str(dv), report_version=str(rv), request_id=_coerce_str(getattr(request.state, 'request_id', None))),
                )
            )
    return ReportsListResponse(total=len(items), items=items)


@router.post('/assistant/resolve-target', response_model=AssistantResolveTargetResponse)
def boundary_assistant_resolve_target(
    body: AssistantResolveTargetRequest,
    request: Request,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'alerts.view', 'tasks.view', 'reports.view', 'decisionlog.view'):
        raise HTTPException(status_code=403)
    try:
        parsed = parse_copilot_target(
            target=body.target,
            data_version=body.data_version,
            section=body.section or '',
            table=body.table or '',
            metric=body.metric or '',
            run_id=body.run_id or '',
            report_version=body.report_version or '',
            fact_id=body.fact_id or '',
            source_id=body.source_id or '',
            request_id=body.request_id or '',
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'error': 'copilot_target_invalid', 'detail': str(exc)})

    dv = str(parsed.get('data_version') or '').strip()
    if not dv:
        raise HTTPException(status_code=400, detail={'error': 'copilot_target_missing_data_version'})

    required_permission = resolve_section_required_permission(parsed.get('section') or '', cfg=load_copilot_tools_config())
    if required_permission and not _user_has_any(user, required_permission):
        raise HTTPException(status_code=403, detail={'error': 'copilot_target_forbidden', 'required_permission': required_permission})

    settings = _runtime_settings()
    cfg = load_copilot_answer_config()
    resolver_cfg = dict(cfg.get('resolver') or {})
    fact_pack = build_fact_pack_for_assistant(
        artifacts_root=settings.artifacts_root,
        data_version=dv,
        asof_date=str(resolver_cfg.get('asof_date') or utc_date_str()),
        period=str(resolver_cfg.get('default_period') or 'daily'),
        web_db_path=settings.storage_dir / 'web.db',
        max_rows=int(resolver_cfg.get('max_rows') or 20),
    )
    resolution = resolve_copilot_target_from_fact_pack(fact_pack=fact_pack, target=parsed)
    target_params = dict(resolution.get('target') or parsed)
    navigation_hints = build_copilot_navigation_hints(target=target_params, resolution=resolution)
    detail_actions = build_copilot_detail_actions(target=target_params, resolution=resolution)
    source_lines: list[str] = []
    for row in list(resolution.get('sources') or []):
        if not isinstance(row, dict):
            continue
        source_id_value = str(row.get('source_id') or '').strip()
        ref_value = str(row.get('ref') or '').strip()
        section_value = str(row.get('section') or '').strip()
        line = f'{source_id_value}: {ref_value}' if source_id_value else ref_value
        if section_value:
            line += f' | section={section_value}'
        if line:
            source_lines.append(line)
    return AssistantResolveTargetResponse(
        target={**target_params, 'api_target_href': build_copilot_api_target(target_params)},
        resolution_summary=str(summarize_target_resolution(resolution) or ''),
        required_permission=required_permission,
        navigation_hints=list(navigation_hints or []),
        detail_actions=list(detail_actions or []),
        source_lines=source_lines,
        fact=dict(resolution.get('fact') or {}),
        table=dict(resolution.get('table') or {}),
        missing_data_request=dict(resolution.get('missing_data_request') or {}),
    )


@router.get('/decisions', response_model=DecisionsListResponse)
def boundary_decisions(
    request: Request,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    related_alert: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(require_permissions('decisionlog.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    payload = list_decisions(
        conn,
        tenant_id=tenant_id,
        object_type=object_type,
        object_id=object_id,
        related_alert=related_alert,
        limit=int(limit),
        offset=int(offset),
    )
    items = [_map_decision(dict(row), request=request) for row in list(payload.get('decisions') or [])]
    return DecisionsListResponse(total=int(payload.get('total') or 0), limit=int(limit), offset=int(offset), items=items)


@router.get('/feedback', response_model=FeedbackListResponse)
def boundary_feedback(
    request: Request,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    recommendation_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    if not _user_has_any(user, 'decisionlog.view', 'tasks.view', 'recommendations.confirm'):
        raise HTTPException(status_code=403)
    tenant_id = user.get('tenant_id', 'default')
    payload = list_feedback(
        conn,
        tenant_id=tenant_id,
        object_type=object_type,
        object_id=object_id,
        recommendation_id=recommendation_id,
        limit=int(limit),
        offset=int(offset),
    )
    metrics_payload = compute_feedback_metrics(conn, tenant_id=tenant_id)
    metrics_raw = dict(metrics_payload.get('metrics') or {})
    metrics = FeedbackMetrics(
        total_feedback=int(metrics_raw.get('total_feedback') or metrics_raw.get('feedback_total') or metrics_raw.get('feedback_events_total') or metrics_raw.get('events_total') or 0),
        accepted_count=int(metrics_raw.get('accepted_count') or 0),
        rejected_count=int(metrics_raw.get('rejected_count') or 0),
        acceptance_rate=float(metrics_raw.get('acceptance_rate') or 0.0),
        median_decision_seconds=_coerce_float(metrics_raw.get('median_decision_seconds')),
    )
    items = [_map_feedback(dict(row), request=request) for row in list(payload.get('items') or payload.get('feedback') or [])]
    return FeedbackListResponse(total=int(payload.get('total') or 0), limit=int(limit), offset=int(offset), metrics=metrics, items=items)


@router.get('/economics', response_model=EconomicsListResponse)
def boundary_economics(
    scenario_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(require_permissions('whatif.scenarios.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    scenarios = list_scenarios(conn, tenant_id=tenant_id, status=scenario_status, limit=int(limit), offset=int(offset))
    reports = list_whatif_reports(conn, tenant_id=tenant_id, limit=int(limit), offset=int(offset))
    scenario_items = [
        EconomicsScenarioItem(
            scenario_id=str(row.get('scenario_id') or ''),
            name=str(row.get('name') or ''),
            status=str(row.get('status') or ''),
            description=_coerce_str(row.get('description')),
            data_version=_coerce_str(row.get('data_version')),
            last_economics_run=_coerce_str(row.get('last_economics_run')),
            report_version=_coerce_str(row.get('report_version')),
            created_at=_coerce_str(row.get('created_at')),
            updated_at=_coerce_str(row.get('updated_at')),
        )
        for row in list(scenarios.get('items') or scenarios.get('scenarios') or [])
    ]
    return EconomicsListResponse(
        scenarios_total=int(scenarios.get('total') or 0),
        reports_total=int(reports.get('total') or 0),
        scenario_items=scenario_items,
        report_items=[dict(row) for row in list(reports.get('items') or reports.get('reports') or [])],
    )


@router.get('/decision-intelligence', response_model=DecisionIntelligenceResponse)
def boundary_decision_intelligence(
    request: Request,
    limit: int = 20,
    conn=Depends(get_db),
    user=Depends(get_current_user),
):
    tenant_id = str(user.get('tenant_id') or 'default')
    if not _user_has_any(user, 'decisionlog.view', 'tasks.view', 'recommendations.confirm'):
        raise HTTPException(status_code=403, detail='forbidden')

    decisions_payload = list_decisions(conn, tenant_id=tenant_id, limit=max(int(limit), 50), offset=0)

    try:
        metrics_payload = compute_feedback_metrics(conn, tenant_id=tenant_id)
    except Exception:
        metrics_payload = {}

    if isinstance(metrics_payload, dict):
        metrics_raw = dict(metrics_payload.get('metrics') or metrics_payload or {})
    else:
        metrics_raw = {}

    decision_rows = [dict(row) for row in list(decisions_payload.get('decisions') or [])]

    linked_alerts = 0
    for row in decision_rows:
        if str(row.get('related_alert') or '').strip():
            linked_alerts += 1

    latest_decisions = []
    for row in decision_rows[: int(limit)]:
        try:
            latest_decisions.append(_map_decision(row, request=request))
        except Exception:
            continue

    summary = DecisionIntelligenceSummary(
        total_decisions=int(decisions_payload.get('total') or len(decision_rows)),
        accepted_feedback=int(metrics_raw.get('accepted_count') or metrics_raw.get('accepted_total') or 0),
        rejected_feedback=int(metrics_raw.get('rejected_count') or metrics_raw.get('rejected_total') or 0),
        acceptance_rate=_coerce_float(metrics_raw.get('acceptance_rate')) or 0.0,
        linked_alerts=linked_alerts,
    )
    return DecisionIntelligenceResponse(
        summary=summary,
        top_actions=[],
        latest_decisions=latest_decisions,
    )


@router.get('/pilot', response_model=PilotResponse)
def boundary_pilot(
    request: Request,
    limit: int = 20,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'reports.view', 'jobs.view', 'audit.view'):
        raise HTTPException(status_code=403)
    settings = _runtime_settings()
    items: list[PilotPackItem] = []
    for data_version, pack_dir in _iter_pilot_pack_dirs(settings.artifacts_root)[: int(limit)]:
        try:
            file_count = sum(1 for p in pack_dir.rglob('*') if p.is_file())
        except Exception:
            file_count = 0
        created_at = None
        try:
            created_at = pack_dir.stat().st_mtime_ns
        except Exception:
            created_at = None
        created_str = None
        if created_at is not None:
            from datetime import datetime, UTC
            created_str = datetime.fromtimestamp(created_at / 1_000_000_000, tz=UTC).isoformat().replace('+00:00', 'Z')
        items.append(PilotPackItem(
            pack_id=pack_dir.name,
            data_version=data_version,
            created_at=created_str,
            status='ready',
            file_count=file_count,
            linkage=ApiLinkage(data_version=data_version, request_id=_coerce_str(getattr(request.state, 'request_id', None))),
            source_paths={'pilot_pack_dir': str(pack_dir)},
        ))
    summary = PilotSummary(
        total_pilot_packs=len(items),
        latest_data_version=items[0].data_version if items else None,
        latest_pack_id=items[0].pack_id if items else None,
    )
    return PilotResponse(summary=summary, items=items)


@router.get('/readiness', response_model=ReadinessResponse)
def boundary_readiness(user=Depends(get_current_user)):
    if not _user_has_any(user, 'audit.view', 'jobs.view', 'reports.view', 'tasks.view'):
        raise HTTPException(status_code=403)
    settings = _runtime_settings()
    profile, checks, source_paths = _build_readiness_checks(settings=settings)
    return ReadinessResponse(profile=profile, summary=_readiness_summary(checks), checks=checks, source_paths=source_paths)


@router.get('/support', response_model=SupportResponse)
def boundary_support(user=Depends(get_current_user)):
    if not _user_has_any(user, 'audit.view', 'jobs.view', 'reports.view', 'tasks.view'):
        raise HTTPException(status_code=403)
    settings = _runtime_settings()
    release_metadata = _runtime_release_metadata()
    try:
        support_payload = build_support_sla_incident_summary(
            project_root=settings.project_root,
            artifacts_root=settings.artifacts_root,
            web_storage_dir=settings.storage_dir,
        )
    except Exception:
        support_payload = {'summary': {}, 'source_paths': {}}
    summary_raw = dict(support_payload.get('summary') or {})
    return SupportResponse(
        release=dict(release_metadata or {}),
        observability=dict(obs_snapshot() or {}),
        summary=SupportSummary(
            open_support_cases=int(summary_raw.get('open_support_cases') or 0),
            open_incidents=int(summary_raw.get('open_incidents') or 0),
            critical_open_incidents=int(summary_raw.get('critical_open_incidents') or 0),
            diagnostics_available=int(summary_raw.get('diagnostics_available') or 0),
            support_bundle_count=int(summary_raw.get('support_bundle_count') or 0),
            release_notes_total=int(summary_raw.get('release_notes_total') or 0),
        ),
        source_paths=dict(support_payload.get('source_paths') or {}),
    )


@router.get('/insights', response_model=InsightsListResponse)
def boundary_insights_list(
    status: Optional[str] = None,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view'):
        raise HTTPException(status_code=403)
    return _list_insights(status=status)


@router.get('/insights/{insight_id}', response_model=InsightItem)
def boundary_insights_get(
    insight_id: str,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view'):
        raise HTTPException(status_code=403)
    item = _get_insight(insight_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f'Insight {insight_id} not found')
    return item


@router.post('/insights/{insight_id}/transition', response_model=InsightItem)
def boundary_insights_transition(
    insight_id: str,
    body: InsightTransitionRequest,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    item = _transition_insight(insight_id, body.status)
    if item is None:
        raise HTTPException(status_code=404, detail=f'Insight {insight_id} not found or invalid status')


@router.post('/timeline/events')
async def boundary_timeline_event_create(
    request: Request,
    user=Depends(get_current_user),
):
    body = await request.json()
    required = {'event_type', 'title', 'date'}
    missing = required - set(body.keys())
    if missing:
        raise HTTPException(status_code=422, detail=f'Missing fields: {missing}')
    event_id = f'TL_{utc_timestamp_compact()}'
    new_event = {
        'timeline_event_id': event_id,
        'date': body['date'],
        'event_type': body['event_type'],
        'title': body['title'],
        'body': body.get('description', ''),
        'source': 'Добавлено вручную',
        'has_impact': False,
        'pending_analysis': True,
        'affected_groups': body.get('affected_groups', []),
    }
    return {'event_id': event_id, 'event': new_event, 'status': 'pending_analysis', 'demo': True}
