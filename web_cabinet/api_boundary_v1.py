from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile

from packages.contracts.integrations_health_v1 import IntegrationPatchRequest
from packages.contracts.api_boundary_v1 import (
    AlertItem,
    AlertsListResponse,
    AnimalAttributes,
    ApiLinkage,
    AssistantResolveTargetRequest,
    AssistantResolveTargetResponse,
    BriefingScheduleRequest,
    BriefingScheduleResponse,
    RecommendedTask,
    RecommendedTasksListResponse,
    WorklistCreateRequest,
    WorklistCreateResponse,
    WorklistsFromRecommendedRequest,
    WorklistsFromRecommendedResponse,
    WorklistsFromRecommendedItem,
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
    FeedingRation,
    FeedingRationsResponse,
    FeedIntakeDrop,
    FeedIntakeDropsResponse,
    DomainLabelsResponse,
    Personnel,
    PersonnelCreateRequest,
    PersonnelListResponse,
    PersonnelResponse,
    PersonnelUpdateRequest,
    HealthEvent,
    HealthMetrics,
    InsightItem,
    InsightSettings,
    InsightsListResponse,
    InsightTransitionRequest,
    InsightUpdateRequest,
    PilotPackItem,
    PilotResponse,
    PilotSummary,
    PlannerPlanItem,
    PlannerResponse,
    PlannerSummary,
    ProfileResponse,
    ProfileSummary,
    QcDismissResponse,
    QcIncident,
    QcIncidentsListResponse,
    ReadinessCheck,
    ReadinessResponse,
    ReadinessSummary,
    ReportItem,
    ReportsListResponse,
    ScanNowResponse,
    SupportResponse,
    SupportSummary,
    UploadCommitRequest,
    UploadCommitResponse,
    UploadPreviewResponse,
    UploadTypesListResponse,
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
from core.workflow.briefing_schedule import (
    get_briefing_schedule,
    upsert_briefing_schedule,
    validate_schedule_input,
)
from core.workflow.personnel import (
    create_personnel as _create_personnel,
    delete_personnel as _delete_personnel,
    list_personnel as _list_personnel,
    update_personnel as _update_personnel,
)
from core.workflow.recommended_tasks import build_recommended_tasks_from_insights
from core.workflow.tasks import create_task as _create_task
from core.domain import TaskCreate as _DomainTaskCreate
from core.workflow.decisions import list_decisions_for_object
from core.workflow.summaries import operational_summary_use_case, overdue_tasks_use_case
from core.workflow.tasks import list_tasks_for_object
from core.audit.events import write_audit
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
from web_cabinet.feeding_v1 import load_rations as _load_rations, project_intake_drops as _project_intake_drops
from .insights_v1 import (
    delete_insight as _delete_insight,
    get_insight as _get_insight,
    get_settings as _get_settings,
    list_insights as _list_insights,
    patch_insight as _patch_insight,
    put_settings as _put_settings,
    transition_insight as _transition_insight,
)
from .observability import snapshot as obs_snapshot
from .qc_v1 import (
    list_incidents as _list_qc_incidents,
    get_incident as _get_qc_incident,
    dismiss_incident as _dismiss_qc_incident,
)
from .uploads_v1 import (
    list_types as _list_upload_types,
    generate_template as _generate_template,
    run_preview as _run_upload_preview,
    commit_rows as _commit_upload_rows,
    TokenExpired,
    TenantMismatch,
)
from .rbac import require_permissions
from .reports_approvals_v1 import list_report_statuses
from .utils import list_data_versions, list_report_versions
from .weekly_plans_v1 import list_pending_approval_weekly_plans, list_weekly_plans, summarize_weekly_plan
from .whatif_reports_v1 import list_reports as list_whatif_reports
from .whatif_scenarios_v1 import list_scenarios

# Demo constants for AI demo mode
_DEMO_ANIMAL_ATTRS: dict[str, dict] = {
    "3142": dict(
        name="Ночка", breed="Голштинская", birth_date="2022-03-15",
        lactation_number=3, days_in_milk=45, last_calving_date="2026-03-12",
        total_calvings=3, reproduction_status="Ожидает",
        group_label="Группа 2", farm_label="Ферма Восток",
    ),
    "4821": dict(
        name="Звёздочка", breed="Айрширская", birth_date="2021-11-20",
        lactation_number=4, days_in_milk=120, last_calving_date="2026-01-05",
        total_calvings=4, reproduction_status="Стельная",
        next_calving_expected="2026-10-12",
        group_label="Группа 1", farm_label="Ферма Восток",
    ),
    "3887": dict(
        name="Роза", breed="Голштинская", birth_date="2023-01-10",
        lactation_number=2, days_in_milk=10, last_calving_date="2026-04-16",
        total_calvings=2, reproduction_status="Осеменена",
        group_label="Группа 3", farm_label="Ферма Запад",
    ),
    "4012": dict(
        name="Ива", breed="Джерсейская", birth_date="2022-07-04",
        lactation_number=2, days_in_milk=10, last_calving_date="2026-04-16",
        total_calvings=2, reproduction_status="Осеменена",
        group_label="Группа 3", farm_label="Ферма Запад",
    ),
}

_DEMO_HEALTH_METRICS: dict[str, dict] = {
    "3142": dict(activity_score=18.0, scc=450, scc_trend="↑", daily_milk_yield_kg=18.2),
    "4821": dict(activity_score=72.0, scc=95, scc_trend="→", daily_milk_yield_kg=24.5, body_condition_score=3.2),
    "3887": dict(activity_score=65.0, scc=120, scc_trend="↓", daily_milk_yield_kg=12.0, body_condition_score=2.8),
    "4012": dict(activity_score=68.0, scc=85, scc_trend="→", daily_milk_yield_kg=11.5, body_condition_score=3.0),
}


def _demo_health_metrics_for(object_id: str) -> dict:
    """Deterministic demo health metrics for any animal_id — keeps profile
    Health tab from being empty when the animal isn't one of the 4 hand-picked
    demo cards. Hash-based so the same id always returns the same numbers.
    """
    if object_id in _DEMO_HEALTH_METRICS:
        return dict(_DEMO_HEALTH_METRICS[object_id])
    import hashlib
    h = hashlib.sha1(object_id.encode("utf-8")).digest()
    # Spread bytes across distinct features so they don't correlate.
    activity = 35.0 + (h[0] % 50)               # 35..85
    scc = 70 + (h[1] % 280) + (h[2] % 80)        # 70..430
    bcs = round(2.4 + (h[3] % 30) / 25.0, 1)     # 2.4..3.6
    yield_kg = round(8.0 + (h[4] % 22) + (h[5] % 5) / 10.0, 1)  # 8..30
    trend = ("↑", "→", "↓")[h[6] % 3]
    return dict(
        activity_score=float(activity),
        scc=int(scc),
        scc_trend=trend,
        daily_milk_yield_kg=yield_kg,
        body_condition_score=bcs,
    )


_DEMO_HEALTH_EVENT_TYPES = ["мастит", "хромота", "кетоз", "метрит", "лечение", "вакцинация"]
_DEMO_HEALTH_SEVERITIES = ["info", "warn", "high"]


def _demo_health_events_for(object_id: str, limit: int = 5) -> list[HealthEvent]:
    """Deterministic mock health events for a given animal id. Used as a
    fallback when dm_health_events has no rows for this animal.
    """
    import hashlib, datetime as _dt
    h = hashlib.sha1(object_id.encode("utf-8")).digest()
    today = _dt.date.today()
    out: list[HealthEvent] = []
    n = max(1, min(limit, 1 + h[7] % limit))
    for i in range(n):
        days_back = 3 + (h[(i * 3) % 20] % 110)
        etype = _DEMO_HEALTH_EVENT_TYPES[h[(i * 5 + 2) % 20] % len(_DEMO_HEALTH_EVENT_TYPES)]
        sev = _DEMO_HEALTH_SEVERITIES[h[(i * 7 + 4) % 20] % 3]
        out.append(HealthEvent(
            event_id=f"demo_he_{object_id}_{i}",
            event_date=(today - _dt.timedelta(days=days_back)).isoformat(),
            event_type=etype,
            severity=sev,
            notes=f"Демо-событие #{i + 1} для {object_id}",
            treatment=None,
        ))
    out.sort(key=lambda e: e.event_date or "", reverse=True)
    return out


def _fetch_dm_health_events(conn, tenant_id: str, object_id: str, limit: int = 10) -> list[HealthEvent]:
    """Pull recent health events for a single animal from dm_health_events.
    Returns [] silently if table missing or query fails — caller decides
    whether to substitute demo events.
    """
    try:
        rows = conn.execute(
            "SELECT event_date, event_type, severity, notes, treatment "
            "FROM dm_health_events "
            "WHERE tenant_id = %s AND animal_id = %s "
            "ORDER BY event_date DESC LIMIT %s",
            (tenant_id, object_id, int(limit)),
        ).fetchall()
    except Exception:
        return []
    out: list[HealthEvent] = []
    for r in rows or []:
        # Both dict and tuple cursor flavours are in play across drivers.
        try:
            ed = r["event_date"]; et = r["event_type"]; sev = r["severity"]
            notes = r.get("notes") if isinstance(r, dict) else r["notes"]
            treat = r.get("treatment") if isinstance(r, dict) else r["treatment"]
        except (KeyError, TypeError, IndexError):
            ed, et, sev, notes, treat = r[0], r[1], r[2], (r[3] if len(r) > 3 else None), (r[4] if len(r) > 4 else None)
        out.append(HealthEvent(
            event_id=None,
            event_date=str(ed) if ed else None,
            event_type=str(et) if et else None,
            severity=str(sev) if sev else None,
            notes=str(notes) if notes else None,
            treatment=str(treat) if treat else None,
        ))
    return out


def _build_db_animal_fields(conn, tenant_id: str, object_id: str) -> tuple:
    """Fetch animal attributes and health metrics from Postgres."""
    import datetime
    row = conn.execute(
        "SELECT breed, birth_date, status, current_pen_id FROM dm_animals "
        "WHERE tenant_id = %s AND animal_id = %s",
        (tenant_id, object_id),
    ).fetchone()
    if not row:
        return None, None

    breed = row['breed']
    birth_date = row['birth_date']
    status = row['status']

    lac = conn.execute(
        "SELECT lactation_no, calving_date FROM dm_lactations "
        "WHERE tenant_id = %s AND animal_id = %s ORDER BY calving_date DESC LIMIT 1",
        (tenant_id, object_id),
    ).fetchone()
    lactation_no = lac['lactation_no'] if lac else None
    calving_date = lac['calving_date'] if lac else None
    dim = (datetime.date.today() - calving_date).days if calving_date else None

    milk_row = conn.execute(
        "SELECT milk_kg, scc_cells_ml FROM dm_milkings_daily "
        "WHERE tenant_id = %s AND animal_id = %s ORDER BY date DESC LIMIT 1",
        (tenant_id, object_id),
    ).fetchone()
    daily_milk = float(milk_row['milk_kg']) if milk_row and milk_row['milk_kg'] is not None else None
    scc = int(milk_row['scc_cells_ml'] / 1000) if milk_row and milk_row['scc_cells_ml'] is not None else None

    attrs = AnimalAttributes(
        breed=breed,
        birth_date=str(birth_date) if birth_date else None,
        lactation_number=lactation_no,
        days_in_milk=dim,
        last_calving_date=str(calving_date) if calving_date else None,
        total_calvings=lactation_no,
        reproduction_status=status,
    )
    metrics = HealthMetrics(
        daily_milk_yield_kg=daily_milk,
        scc=scc,
        scc_trend="→",
    )
    return attrs, metrics


def _build_demo_animal_fields(object_id: str) -> tuple:
    attrs_data = _DEMO_ANIMAL_ATTRS.get(object_id)
    attrs = AnimalAttributes(**attrs_data) if attrs_data else None
    metrics = HealthMetrics(**_demo_health_metrics_for(object_id))
    return attrs, metrics

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
        source_insight_id=_coerce_str(row.get('source_insight_id')),
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


@router.get('/animals')
def boundary_animals_list(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    breed: Optional[str] = None,
    status: Optional[str] = None,
    pen_id: Optional[str] = None,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    try:
        where = "WHERE tenant_id = %s"
        params: list = [tenant_id]
        if search:
            where += " AND animal_id ILIKE %s"
            params.append(f"%{search}%")
        if breed:
            where += " AND breed ILIKE %s"
            params.append(f"%{breed}%")
        if status:
            where += " AND status = %s"
            params.append(status)
        if pen_id:
            where += " AND current_pen_id ILIKE %s"
            params.append(f"%{pen_id}%")
        rows = conn.execute(
            f"SELECT animal_id, breed, status, current_pen_id FROM dm_animals {where} ORDER BY animal_id LIMIT %s OFFSET %s",
            tuple(params) + (limit, offset),
        ).fetchall()
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM dm_animals {where}",
            tuple(params),
        ).fetchone()
        total = count_row[0] if count_row else 0
        animals = [
            {
                "animal_id": r[0],
                "breed": r[1] or "—",
                "status": r[2] or "active",
                "pen_id": r[3] or "—",
            }
            for r in rows
        ]
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("animals list failed: %s", exc)
        animals = []
        total = 0
    return {"animals": animals, "total": total, "limit": limit, "offset": offset}


@router.get('/animals/filter-options')
def boundary_animals_filter_options(
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    """Returns unique values for breed, status, pen_id columns for filter dropdowns."""
    tenant_id = user.get('tenant_id', 'default')
    try:
        breeds = [r[0] for r in conn.execute(
            "SELECT DISTINCT breed FROM dm_animals WHERE tenant_id = %s AND breed IS NOT NULL ORDER BY breed",
            (tenant_id,),
        ).fetchall()]
        statuses = [r[0] for r in conn.execute(
            "SELECT DISTINCT status FROM dm_animals WHERE tenant_id = %s AND status IS NOT NULL ORDER BY status",
            (tenant_id,),
        ).fetchall()]
        pen_ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT current_pen_id FROM dm_animals WHERE tenant_id = %s AND current_pen_id IS NOT NULL ORDER BY current_pen_id",
            (tenant_id,),
        ).fetchall()]
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("animals filter-options failed: %s", exc)
        breeds, statuses, pen_ids = [], [], []
    return {"breeds": breeds, "statuses": statuses, "pen_ids": pen_ids}


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
    owner_user_id: Optional[int] = None,
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
        owner_user_id=owner_user_id,
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

    animal_attributes = None
    health_metrics = None
    recent_health_events: list[HealthEvent] = []
    if object_type == 'animal':
        try:
            from web_cabinet.ai.config import get_ai_settings as _get_ai
            if _get_ai().GENOMEAI_AI_DEMO_MODE:
                animal_attributes, health_metrics = _build_demo_animal_fields(object_id)
            else:
                animal_attributes, health_metrics = _build_db_animal_fields(conn, tenant_id, object_id)
                # In DB mode, still fall back to deterministic demo metrics
                # if the DB has no record for this animal — keeps the Health
                # tab from showing an empty card.
                if health_metrics is None:
                    health_metrics = HealthMetrics(**_demo_health_metrics_for(object_id))
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning("animal fields failed: %s", exc)
            health_metrics = HealthMetrics(**_demo_health_metrics_for(object_id))

        recent_health_events = _fetch_dm_health_events(conn, tenant_id, object_id, limit=10)
        if not recent_health_events:
            recent_health_events = _demo_health_events_for(object_id, limit=5)

    return ProfileResponse(
        entity=EntityRef(object_type=object_type, object_id=object_id),
        summary=ProfileSummary(alerts_open=alerts_open, worklists_open=worklists_open, decisions_total=len(decisions)),
        alerts=alerts,
        worklists=worklists,
        decisions=decisions,
        animal_attributes=animal_attributes,
        health_metrics=health_metrics,
        recent_health_events=recent_health_events,
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
        web_db_path=None,
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
    farm_id: str = 'INV_FARM_001',
    category: Optional[str] = None,
    severity_min: Optional[str] = None,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view'):
        raise HTTPException(status_code=403)
    user_id = str(user.get('user_id') or user.get('username') or 'unknown')
    return _list_insights(
        farm_id=farm_id,
        status=status,
        user_id=user_id,
        category=category,
        severity_min=severity_min,
    )


# NOTE: Fixed-path /insights/* routes (settings, scan-now) MUST be registered
# before /insights/{insight_id}, otherwise FastAPI matches them as
# insight_id="settings" / "scan-now" against the path-parameterized handler.
@router.get('/insights/settings', response_model=InsightSettings)
def boundary_insights_settings_get(
    farm_id: str,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view'):
        raise HTTPException(status_code=403)
    user_id = str(user.get('user_id') or user.get('username') or 'unknown')
    return _get_settings(user_id=user_id, farm_id=farm_id)


@router.put('/insights/settings', response_model=InsightSettings)
def boundary_insights_settings_put(
    body: InsightSettings,
    farm_id: str,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view'):
        raise HTTPException(status_code=403)
    user_id = str(user.get('user_id') or user.get('username') or 'unknown')
    return _put_settings(user_id=user_id, farm_id=farm_id, settings=body)


@router.post('/insights/scan-now', response_model=ScanNowResponse)
def boundary_insights_scan_now(
    farm_id: str = 'INV_FARM_001',
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    import os as _os
    from web_cabinet.ai.background.insight_scanner import scan_for_new_insights

    redis_url = _os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0')
    client = None
    try:
        import redis as _redis  # type: ignore
        client = _redis.Redis.from_url(redis_url)
    except Exception:
        client = None  # Redis pkg or connection unavailable

    lock_key = f'insight_scanner:lock:{farm_id}'
    acquired = False
    if client is not None:
        try:
            acquired = bool(client.set(lock_key, '1', nx=True, ex=120))
            if not acquired:
                raise HTTPException(status_code=409, detail='scan_in_progress')
        except HTTPException:
            raise
        except Exception:
            client = None  # network blip — best-effort: run without lock

    try:
        insights = scan_for_new_insights(farm_id)
        return ScanNowResponse(
            count=len(insights),
            insight_ids=[i.insight_id for i in insights],
            skipped=False,
        )
    finally:
        if client is not None and acquired:
            try:
                client.delete(lock_key)
            except Exception:
                pass


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
    return item


@router.patch('/insights/{insight_id}', response_model=InsightItem)
def boundary_insights_patch(
    insight_id: str,
    body: InsightUpdateRequest,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    edited_by = str(user.get('username') or user.get('user_id') or 'unknown')
    item = _patch_insight(
        insight_id,
        title=body.title,
        body=body.body,
        action=body.action,
        recommendations=[r.model_dump() for r in body.recommendations] if body.recommendations else None,
        edited_by=edited_by,
    )
    if item is None:
        raise HTTPException(status_code=404, detail=f'Insight {insight_id} not found or deleted')
    return item


@router.delete('/insights/{insight_id}')
def boundary_insights_delete(
    insight_id: str,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    _delete_insight(insight_id)
    return {"ok": True, "insight_id": insight_id}


_ROLE_TO_TEAM: dict[str, str] = {
    'Vet': 'team-health',
    'Zootech': 'team-data',
    'Director': 'team-econ',
}
_DOMAIN_TO_TEAM: dict[str, str] = {
    'health': 'team-health',
    'welfare': 'team-health',
    'reproduction': 'team-repro',
    'production': 'team-data',
    'feeding': 'team-data',
    'economics': 'team-econ',
}


def _team_for_role_or_domain(*, role: Optional[str], domain: Optional[str]) -> Optional[str]:
    if role and role in _ROLE_TO_TEAM:
        return _ROLE_TO_TEAM[role]
    if domain and str(domain).lower() in _DOMAIN_TO_TEAM:
        return _DOMAIN_TO_TEAM[str(domain).lower()]
    return None


@router.post('/worklists/from-recommended', response_model=WorklistsFromRecommendedResponse)
def boundary_worklists_from_recommended(
    body: WorklistsFromRecommendedRequest,
    request: Request,
    user=Depends(require_permissions('tasks.write')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    out_items: list[WorklistsFromRecommendedItem] = []
    created_count = 0
    reused_count = 0

    for rec in body.items:
        if not rec.source_insight_id or not rec.recommended_task_id:
            raise HTTPException(
                status_code=400,
                detail={'error': 'recommended_task.invalid', 'detail': 'source_insight_id and recommended_task_id are required'},
            )
        dedupe_key = f'insight:{rec.source_insight_id}:{rec.recommended_task_id}'

        existing = conn.execute(
            "SELECT task_id FROM tasks_v1 WHERE tenant_id=? AND dedupe_key=? LIMIT 1",
            (tenant_id, dedupe_key),
        ).fetchone()
        if existing:
            out_items.append(WorklistsFromRecommendedItem(
                recommended_task_id=rec.recommended_task_id,
                source_insight_id=rec.source_insight_id,
                task_id=str(dict(existing)['task_id']),
                created=False,
            ))
            reused_count += 1
            continue

        team = _team_for_role_or_domain(role=rec.assignee_role, domain=rec.domain)
        task_payload = _DomainTaskCreate(
            task_type='insight_followup',
            title=rec.title,
            domain=rec.domain,
            priority=int(rec.priority or 3),
            due_at=rec.due_at,
            owner_user_id=rec.assignee_user_id,
            assignee_team=team,
            related_alert=rec.source_insight_id,
            why={
                'summary': rec.why_summary,
                'description': rec.description or '',
                'assignee_role_hint': rec.assignee_role or '',
            },
            dedupe_key=dedupe_key,
            source_insight_id=rec.source_insight_id,
        )
        new_task_id = _create_task(conn, tenant_id=tenant_id, t=task_payload)
        out_items.append(WorklistsFromRecommendedItem(
            recommended_task_id=rec.recommended_task_id,
            source_insight_id=rec.source_insight_id,
            task_id=new_task_id,
            created=True,
        ))
        created_count += 1

    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='tasks.bulk_create_from_insights',
            object_type='tasks_v1',
            object_id=f'bulk:{created_count}+{reused_count}',
            before=None,
            after={'created': created_count, 'reused': reused_count, 'items': [i.model_dump() for i in out_items]},
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass

    return WorklistsFromRecommendedResponse(
        total=len(out_items),
        created=created_count,
        reused=reused_count,
        items=out_items,
    )


@router.post('/worklists', response_model=WorklistCreateResponse, status_code=201)
def boundary_worklists_create(
    body: WorklistCreateRequest,
    request: Request,
    user=Depends(require_permissions('tasks.write')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    title = (body.title or '').strip()
    if not title:
        raise HTTPException(status_code=400, detail={'error': 'worklists.invalid', 'detail': 'title is required'})
    priority = int(body.priority or 3)
    if priority < 1 or priority > 5:
        raise HTTPException(status_code=400, detail={'error': 'worklists.invalid', 'detail': 'priority must be in 1..5'})
    task_payload = _DomainTaskCreate(
        task_type='manual',
        title=title,
        domain=body.domain,
        priority=priority,
        due_at=body.due_at,
        owner_user_id=body.owner_user_id,
        assignee_team=(body.assignee_team.strip() if body.assignee_team else None),
        why={'summary': body.description or '', 'source': 'manual.team_fab'},
    )
    new_task_id = _create_task(conn, tenant_id=tenant_id, t=task_payload)
    row = conn.execute(
        "SELECT * FROM tasks_v1 WHERE tenant_id=? AND task_id=?",
        (tenant_id, new_task_id),
    ).fetchone()
    item = _map_worklist(dict(row), request=request) if row else None
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='tasks.create.manual',
            object_type='tasks_v1',
            object_id=new_task_id,
            after={
                'task_id': new_task_id,
                'title': title,
                'domain': body.domain,
                'priority': priority,
                'owner_user_id': body.owner_user_id,
                'assignee_team': body.assignee_team,
                'has_due_at': body.due_at is not None,
            },
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass
    if item is None:
        raise HTTPException(status_code=500, detail={'error': 'worklists.create.lost_row', 'detail': 'task created but row missing'})
    return WorklistCreateResponse(task_id=new_task_id, item=item)


@router.get('/recommended-tasks', response_model=RecommendedTasksListResponse)
def boundary_recommended_tasks_list(
    farm_id: str = 'INV_FARM_001',
    status: Optional[str] = None,
    category: Optional[str] = None,
    severity_min: Optional[str] = None,
    only_active: bool = True,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view'):
        raise HTTPException(status_code=403)
    user_id = str(user.get('user_id') or user.get('username') or 'unknown')
    insights_resp = _list_insights(
        farm_id=farm_id,
        status=status,
        user_id=user_id,
        category=category,
        severity_min=severity_min,
    )
    proposals = build_recommended_tasks_from_insights(
        insights_resp.items,
        only_active=bool(only_active),
    )
    return RecommendedTasksListResponse(
        total=len(proposals),
        items=[RecommendedTask(**p) for p in proposals],
    )


@router.get('/feeding/rations', response_model=FeedingRationsResponse)
def boundary_feeding_rations(
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'kpi.view'):
        raise HTTPException(status_code=403)
    cfg_path = Path(__file__).resolve().parents[1] / 'configs' / 'feeding' / 'rations_v1.yaml'
    items = _load_rations(cfg_path)
    return FeedingRationsResponse(total=len(items), items=items)


@router.get('/feeding/intake-drops', response_model=FeedIntakeDropsResponse)
def boundary_feeding_intake_drops(
    farm_id: str = 'INV_FARM_001',
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'kpi.view'):
        raise HTTPException(status_code=403)
    user_id = str(user.get('user_id') or user.get('username') or 'unknown')
    insights_resp = _list_insights(farm_id=farm_id, user_id=user_id)
    items = _project_intake_drops(insights_resp.items)
    return FeedIntakeDropsResponse(total=len(items), items=items)


@router.get('/catalogs/domain-labels', response_model=DomainLabelsResponse)
def boundary_catalogs_domain_labels(
    locale: Optional[str] = None,
    user=Depends(get_current_user),
):
    from core.workflow.domain_labels import default_locale, load_domain_labels
    resolved_locale = (locale or default_locale()).strip().lower()
    labels = load_domain_labels(resolved_locale)
    return DomainLabelsResponse(locale=resolved_locale, labels=labels)


@router.get('/qc/incidents', response_model=QcIncidentsListResponse)
def boundary_qc_incidents_list(
    farm_id: str = 'INV_FARM_001',
    metric_id: Optional[str] = None,
    active: bool = True,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view'):
        raise HTTPException(status_code=403)
    return _list_qc_incidents(farm_id=farm_id, metric_id=metric_id, active=active)


@router.get('/qc/incidents/{incident_id}', response_model=QcIncident)
def boundary_qc_incident_get(
    incident_id: str,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view'):
        raise HTTPException(status_code=403)
    item = _get_qc_incident(incident_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f'QC incident {incident_id} not found')
    return item


@router.post('/qc/incidents/{incident_id}/dismiss', response_model=QcDismissResponse)
def boundary_qc_incident_dismiss(
    incident_id: str,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'alerts.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    _dismiss_qc_incident(incident_id)
    return QcDismissResponse(incident_id=incident_id, status='dismissed')


@router.get('/uploads/types', response_model=UploadTypesListResponse)
def boundary_uploads_types(user=Depends(get_current_user)):
    if not _user_has_any(user, 'tasks.view'):
        raise HTTPException(status_code=403)
    return UploadTypesListResponse(items=_list_upload_types())


@router.get('/uploads/template')
def boundary_uploads_template(
    type: str = Query(...),
    fmt: str = Query('csv'),
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view'):
        raise HTTPException(status_code=403)
    try:
        body, content_type, filename = _generate_template(type, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=body,
        media_type=content_type,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('/uploads/preview', response_model=UploadPreviewResponse)
async def boundary_uploads_preview(
    type: str = Query(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    body = await file.read()
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='file_too_large')
    tenant_id = str(user.get('tenant_id') or 'default')
    return _run_upload_preview(type, body, file.filename or 'upload', tenant_id)


@router.post('/uploads/commit', response_model=UploadCommitResponse)
def boundary_uploads_commit(
    body: UploadCommitRequest,
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'tasks.view', 'tasks.create'):
        raise HTTPException(status_code=403)
    tenant_id = str(user.get('tenant_id') or 'default')
    farm_id = user.get('farm_id')
    try:
        return _commit_upload_rows(
            body.preview_token, tenant_id=tenant_id, farm_id=farm_id,
        )
    except TokenExpired:
        raise HTTPException(status_code=410, detail='token_expired')
    except TenantMismatch:
        raise HTTPException(status_code=403, detail='tenant_mismatch')


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


def _briefing_response(payload: dict) -> BriefingScheduleResponse:
    return BriefingScheduleResponse(
        tenant_id=str(payload.get('tenant_id') or 'default'),
        periodicity=str(payload.get('periodicity') or 'weekly'),
        time_of_day=str(payload.get('time_of_day') or '07:00'),
        auto_create_tasks=bool(payload.get('auto_create_tasks') or False),
        updated_at=payload.get('updated_at'),
        updated_by=payload.get('updated_by'),
    )


@router.get('/briefing/schedule', response_model=BriefingScheduleResponse)
def boundary_briefing_schedule_get(
    user=Depends(require_permissions('briefing.schedule.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    return _briefing_response(get_briefing_schedule(conn, tenant_id=tenant_id))


@router.put('/briefing/schedule', response_model=BriefingScheduleResponse)
def boundary_briefing_schedule_put(
    body: BriefingScheduleRequest,
    request: Request,
    user=Depends(require_permissions('briefing.schedule.manage')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    err = validate_schedule_input(periodicity=body.periodicity, time_of_day=body.time_of_day)
    if err:
        raise HTTPException(status_code=400, detail={'error': 'briefing.schedule.invalid', 'detail': err})

    before, after = upsert_briefing_schedule(
        conn,
        tenant_id=tenant_id,
        periodicity=body.periodicity,
        time_of_day=body.time_of_day,
        auto_create_tasks=body.auto_create_tasks,
        user_id=user.get('user_id') or 0,
    )
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='briefing.schedule.update',
            object_type='briefing_schedule',
            object_id=tenant_id,
            before=before,
            after=after,
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass
    return _briefing_response(after)


def _personnel_record_to_pydantic(rec) -> Personnel:
    """Convert core.domain.records.Personnel (dataclass) → contracts.Personnel (pydantic)."""
    return Personnel(
        personnel_id=rec.personnel_id,
        full_name=rec.full_name,
        position=rec.position,
        group_id=rec.group_id,
        photo_ref=rec.photo_ref,
        phone=rec.phone,
        email=rec.email,
        hired_at=rec.hired_at,
        user_id=rec.user_id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


@router.get('/personnel', response_model=PersonnelListResponse)
def boundary_personnel_list(
    request: Request,
    group_id: Optional[str] = Query(default=None),
    has_user: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_permissions('personnel.read')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    pii_visible = bool(core_has_any_permission(user.get('permissions') or [], 'personnel.read_pii'))
    total, items = _list_personnel(
        conn,
        tenant_id=tenant_id,
        group_id=group_id,
        has_user=has_user,
        limit=limit,
        offset=offset,
        pii_visible=pii_visible,
    )
    if pii_visible and total > 0:
        try:
            write_audit(
                conn,
                tenant_id=tenant_id,
                user_id=int(user.get('user_id') or 0),
                username=str(user.get('username') or ''),
                role=str(user.get('role') or ''),
                action='personnel.list.pii_view',
                object_type='personnel',
                object_id=None,
                after={'count': total, 'group_id': group_id},
                ip=getattr(request.client, 'host', None) if request.client else None,
                user_agent=request.headers.get('user-agent'),
                request_id=getattr(request.state, 'request_id', None),
            )
        except Exception:
            pass
    return PersonnelListResponse(
        total=total,
        pii_visible=pii_visible,
        items=[_personnel_record_to_pydantic(it) for it in items],
    )


@router.post('/personnel', response_model=PersonnelResponse, status_code=201)
def boundary_personnel_create(
    body: PersonnelCreateRequest,
    request: Request,
    user=Depends(require_permissions('personnel.manage')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    if not (body.full_name or '').strip():
        raise HTTPException(status_code=400, detail={'error': 'personnel.invalid', 'detail': 'full_name is required'})
    if not (body.position or '').strip():
        raise HTTPException(status_code=400, detail={'error': 'personnel.invalid', 'detail': 'position is required'})
    rec = _create_personnel(
        conn,
        tenant_id=tenant_id,
        full_name=body.full_name.strip(),
        position=body.position.strip(),
        group_id=(body.group_id.strip() if body.group_id else None),
        phone=(body.phone.strip() if body.phone else None),
        email=(body.email.strip() if body.email else None),
        hired_at=(body.hired_at.strip() if body.hired_at else None),
        user_id=body.user_id,
    )
    pii_visible = bool(core_has_any_permission(user.get('permissions') or [], 'personnel.read_pii'))
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='personnel.create',
            object_type='personnel',
            object_id=rec.personnel_id,
            after={
                'personnel_id': rec.personnel_id,
                'full_name': rec.full_name,
                'position': rec.position,
                'group_id': rec.group_id,
                'user_id': rec.user_id,
                'has_phone': rec.phone is not None,
                'has_email': rec.email is not None,
                'has_hired_at': rec.hired_at is not None,
            },
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass
    item = _personnel_record_to_pydantic(rec if pii_visible else rec.masked())
    return PersonnelResponse(pii_visible=pii_visible, item=item)


def _personnel_audit_snapshot(rec) -> dict[str, Any]:
    """Audit-safe snapshot: avoid mirroring PII into audit_log payload."""
    return {
        'personnel_id': rec.personnel_id,
        'full_name': rec.full_name,
        'position': rec.position,
        'group_id': rec.group_id,
        'user_id': rec.user_id,
        'has_phone': rec.phone is not None,
        'has_email': rec.email is not None,
        'has_hired_at': rec.hired_at is not None,
        'has_photo': rec.photo_ref is not None,
    }


@router.patch('/personnel/{personnel_id}', response_model=PersonnelResponse)
def boundary_personnel_update(
    personnel_id: str,
    body: PersonnelUpdateRequest,
    request: Request,
    user=Depends(require_permissions('personnel.manage')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(
            status_code=400,
            detail={'error': 'personnel.invalid', 'detail': 'no fields to update'},
        )
    before, after = _update_personnel(
        conn,
        tenant_id=tenant_id,
        personnel_id=personnel_id,
        patch=patch,
    )
    if before is None:
        raise HTTPException(
            status_code=404,
            detail={'error': 'personnel.not_found', 'detail': 'personnel_id not found'},
        )
    final = after or before
    pii_visible = bool(core_has_any_permission(user.get('permissions') or [], 'personnel.read_pii'))
    if after is not None:
        try:
            write_audit(
                conn,
                tenant_id=tenant_id,
                user_id=int(user.get('user_id') or 0),
                username=str(user.get('username') or ''),
                role=str(user.get('role') or ''),
                action='personnel.update',
                object_type='personnel',
                object_id=personnel_id,
                before=_personnel_audit_snapshot(before),
                after=_personnel_audit_snapshot(after),
                ip=getattr(request.client, 'host', None) if request.client else None,
                user_agent=request.headers.get('user-agent'),
                request_id=getattr(request.state, 'request_id', None),
            )
        except Exception:
            pass
    item = _personnel_record_to_pydantic(final if pii_visible else final.masked())
    return PersonnelResponse(pii_visible=pii_visible, item=item)


@router.delete('/personnel/{personnel_id}', status_code=204)
def boundary_personnel_delete(
    personnel_id: str,
    request: Request,
    user=Depends(require_permissions('personnel.manage')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    deleted = _delete_personnel(conn, tenant_id=tenant_id, personnel_id=personnel_id)
    if deleted is None:
        raise HTTPException(
            status_code=404,
            detail={'error': 'personnel.not_found', 'detail': 'personnel_id not found'},
        )
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='personnel.delete',
            object_type='personnel',
            object_id=personnel_id,
            before=_personnel_audit_snapshot(deleted),
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass
    return Response(status_code=204)


# ---- P1-6: Integrations health (read-only) + P1-6b slice 1: admin enable/disable ----


@router.get('/integrations/health')
def boundary_integrations_health(
    user=Depends(require_permissions('integrations.view')),
    conn=Depends(get_db),
):
    """Aggregate health snapshot across LLM, batch connectors, IoT stubs, RU stubs.

    Each row matches `packages.contracts.integrations_health_v1.IntegrationHealth`.
    P1-6b slice 1: rows admins have switched off in `integration_overrides_v1`
    surface as status='disabled' with an admin note (manual sync, deep-link logs
    arrive in subsequent P1-6b slices).
    """
    # Lazy import to ensure bundled providers register themselves.
    from core.interoperability import providers as _providers  # noqa: F401
    from core.interoperability.integrations_health import collect_health
    from core.workflow.integration_overrides import apply_overrides, list_overrides_for_tenant

    tenant_id = str(user.get('tenant_id') or 'default')
    items = collect_health(conn, tenant_id=tenant_id)
    overrides = list_overrides_for_tenant(conn, tenant_id=tenant_id)
    items = apply_overrides(items, overrides)
    return {
        'schema': 'genomeai.api.integrations.health.v1',
        'items': [item.model_dump() for item in items],
        'total': len(items),
    }


@router.post('/integrations/{integration_id}/sync')
def boundary_integration_sync(
    integration_id: str,
    request: Request,
    user=Depends(require_permissions('integrations.manage')),
    conn=Depends(get_db),
):
    """Trigger a manual sync for one integration row (P1-6b slice 2).

    Currently supports LLM ping only (`llm.*`); other ids return 400 with
    `not_supported`. Always writes an audit event `integration.manual_sync`
    capturing the outcome so admins can see what fired and when.
    """
    from core.interoperability import providers as _providers  # noqa: F401
    from core.interoperability.integrations_health import collect_health
    from core.workflow.integration_sync import trigger_sync

    tenant_id = str(user.get('tenant_id') or 'default')

    known_ids = {item.id for item in collect_health(conn, tenant_id=tenant_id)}
    if integration_id not in known_ids:
        raise HTTPException(
            status_code=404,
            detail={'error': 'integration.unknown', 'integration_id': integration_id},
        )

    result = trigger_sync(conn, integration_id=integration_id, tenant_id=tenant_id)
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='integration.manual_sync',
            object_type='integration',
            object_id=integration_id,
            before=None,
            after={
                'ok': bool(result.get('ok')),
                'message': result.get('message'),
                'duration_ms': result.get('duration_ms'),
            },
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass

    if not result.get('ok') and result.get('message') == 'not_supported':
        raise HTTPException(status_code=400, detail={'error': 'sync.not_supported', **result})
    return {'integration_id': integration_id, **result}


@router.patch('/integrations/{integration_id}')
def boundary_integration_patch(
    integration_id: str,
    body: IntegrationPatchRequest,
    request: Request,
    user=Depends(require_permissions('integrations.manage')),
    conn=Depends(get_db),
):
    """Admin enable/disable for an integration row (P1-6b slice 1).

    Persists the override in `integration_overrides_v1` and writes an audit
    event. The change is reflected in the next /integrations/health response.
    """
    from core.interoperability import providers as _providers  # noqa: F401
    from core.interoperability.integrations_health import collect_health
    from core.workflow.integration_overrides import upsert_override

    tenant_id = str(user.get('tenant_id') or 'default')

    # Validate that integration_id is a known provider row for this tenant.
    known_ids = {item.id for item in collect_health(conn, tenant_id=tenant_id)}
    if integration_id not in known_ids:
        raise HTTPException(
            status_code=404,
            detail={'error': 'integration.unknown', 'integration_id': integration_id},
        )

    before, after = upsert_override(
        conn,
        integration_id=integration_id,
        tenant_id=tenant_id,
        enabled=body.enabled,
        user_id=user.get('user_id') or 0,
        username=str(user.get('username') or ''),
    )
    try:
        write_audit(
            conn,
            tenant_id=tenant_id,
            user_id=int(user.get('user_id') or 0),
            username=str(user.get('username') or ''),
            role=str(user.get('role') or ''),
            action='integration.toggle.enable' if body.enabled else 'integration.toggle.disable',
            object_type='integration',
            object_id=integration_id,
            before=before,
            after=after,
            ip=getattr(request.client, 'host', None) if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except Exception:
        pass
    return after
