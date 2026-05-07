from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ApiLinkage(BaseModel):
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    request_id: Optional[str] = None


class EntityRef(BaseModel):
    object_type: str
    object_id: str
    farm_id: Optional[str] = None
    group_id: Optional[str] = None
    label: Optional[str] = None


class AlertItem(BaseModel):
    alert_id: str
    status: str
    alert_type: str
    title: str
    source: Optional[str] = None
    cause: Optional[str] = None
    confidence: Optional[float] = None
    severity: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_username: Optional[str] = None
    deadline: Optional[str] = None
    entity: EntityRef
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)
    why: dict[str, Any] = Field(default_factory=dict)
    what_to_do: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AlertsListResponse(BaseModel):
    schema: str = 'genomeai.api.alerts.list.v1'
    total: int
    limit: int
    offset: int
    items: list[AlertItem] = Field(default_factory=list)


class WorklistItem(BaseModel):
    task_id: str
    status: str
    task_type: str
    title: str
    domain: Optional[str] = None
    priority: int = 3
    due_at: Optional[str] = None
    stage: Optional[str] = None
    assignee_team: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_username: Optional[str] = None
    related_alert: Optional[str] = None
    worklist_type: Optional[str] = None
    confidence: Optional[float] = None
    entity: Optional[EntityRef] = None
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)
    why: dict[str, Any] = Field(default_factory=dict)
    what_to_do: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_overdue: Optional[bool] = None


class WorklistsListResponse(BaseModel):
    schema: str = 'genomeai.api.worklists.list.v1'
    total: int
    limit: int
    offset: int
    items: list[WorklistItem] = Field(default_factory=list)


class PlannerPlanItem(BaseModel):
    plan_id: str
    status: str
    name: str
    week_start: str
    item_count: int = 0
    citation_count: int = 0
    farm_id: Optional[str] = None
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)
    approval_requested_at: Optional[str] = None
    approval_requested_by_username: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by_username: Optional[str] = None


class PlannerSummary(BaseModel):
    alerts_new: int = 0
    alerts_acknowledged: int = 0
    alerts_resolved: int = 0
    tasks_open: int = 0
    tasks_done: int = 0
    overdue_active: int = 0


class PlannerResponse(BaseModel):
    schema: str = 'genomeai.api.planner.v1'
    summary: PlannerSummary
    pending_approvals: int = 0
    weekly_plans: list[PlannerPlanItem] = Field(default_factory=list)
    overdue_items: list[WorklistItem] = Field(default_factory=list)


class DecisionItem(BaseModel):
    decision_id: str
    created_at: str
    action: str
    username: str
    user_id: Optional[int] = None
    reason: Optional[str] = None
    comment: Optional[str] = None
    related_alert: Optional[str] = None
    recommendation_id: Optional[str] = None
    entity: Optional[EntityRef] = None
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionsListResponse(BaseModel):
    schema: str = 'genomeai.api.decisions.list.v1'
    total: int
    limit: int
    offset: int
    items: list[DecisionItem] = Field(default_factory=list)


class DecisionIntelligenceSummary(BaseModel):
    total_decisions: int = 0
    accepted_feedback: int = 0
    rejected_feedback: int = 0
    acceptance_rate: float = 0.0
    linked_alerts: int = 0


class DecisionIntelligenceTopAction(BaseModel):
    action: str
    count: int = 0


class DecisionIntelligenceResponse(BaseModel):
    schema: str = 'genomeai.api.decision_intelligence.summary.v1'
    summary: DecisionIntelligenceSummary = Field(default_factory=DecisionIntelligenceSummary)
    top_actions: list[DecisionIntelligenceTopAction] = Field(default_factory=list)
    latest_decisions: list[DecisionItem] = Field(default_factory=list)


class FeedbackItem(BaseModel):
    feedback_id: str
    created_at: str
    decision: str
    reason_code: str
    comment: Optional[str] = None
    recommendation_id: Optional[str] = None
    related_alert: Optional[str] = None
    task_id: Optional[str] = None
    entity: Optional[EntityRef] = None
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)
    feedback_source: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackMetrics(BaseModel):
    total_feedback: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    acceptance_rate: float = 0.0
    median_decision_seconds: Optional[float] = None


class FeedbackListResponse(BaseModel):
    schema: str = 'genomeai.api.feedback.list.v1'
    total: int
    limit: int
    offset: int
    metrics: FeedbackMetrics = Field(default_factory=FeedbackMetrics)
    items: list[FeedbackItem] = Field(default_factory=list)


class ReportItem(BaseModel):
    data_version: str
    report_version: str
    status: str
    approved_at: Optional[str] = None
    approved_by_username: Optional[str] = None
    comment: Optional[str] = None
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)


class ReportsListResponse(BaseModel):
    schema: str = 'genomeai.api.reports.list.v1'
    total: int
    items: list[ReportItem] = Field(default_factory=list)


class EconomicsScenarioItem(BaseModel):
    scenario_id: str
    name: str
    status: str
    description: Optional[str] = None
    data_version: Optional[str] = None
    last_economics_run: Optional[str] = None
    report_version: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class EconomicsListResponse(BaseModel):
    schema: str = 'genomeai.api.economics.list.v1'
    scenarios_total: int
    reports_total: int
    scenario_items: list[EconomicsScenarioItem] = Field(default_factory=list)
    report_items: list[dict[str, Any]] = Field(default_factory=list)


class AnimalAttributes(BaseModel):
    name: Optional[str] = None
    breed: Optional[str] = None
    birth_date: Optional[str] = None         # YYYY-MM-DD
    lactation_number: Optional[int] = None
    days_in_milk: Optional[int] = None
    last_calving_date: Optional[str] = None  # YYYY-MM-DD
    total_calvings: Optional[int] = None
    reproduction_status: Optional[str] = None
    next_calving_expected: Optional[str] = None
    group_label: Optional[str] = None
    farm_label: Optional[str] = None


class HealthMetrics(BaseModel):
    activity_score: Optional[float] = None
    activity_norm: Optional[float] = 60.0
    scc: Optional[int] = None
    scc_trend: Optional[str] = None
    body_condition_score: Optional[float] = None
    daily_milk_yield_kg: Optional[float] = None


class ProfileSummary(BaseModel):
    alerts_open: int = 0
    worklists_open: int = 0
    decisions_total: int = 0


class ProfileResponse(BaseModel):
    schema: str = 'genomeai.api.profile.v1'
    entity: EntityRef
    summary: ProfileSummary
    alerts: list[AlertItem] = Field(default_factory=list)
    worklists: list[WorklistItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    animal_attributes: Optional[AnimalAttributes] = None
    health_metrics: Optional[HealthMetrics] = None


class AssistantResolveTargetRequest(BaseModel):
    target: Optional[str] = None
    data_version: str
    section: Optional[str] = None
    table: Optional[str] = None
    metric: Optional[str] = None
    run_id: Optional[str] = None
    report_version: Optional[str] = None
    fact_id: Optional[str] = None
    source_id: Optional[str] = None
    request_id: Optional[str] = None


class AssistantResolveTargetResponse(BaseModel):
    schema: str = 'genomeai.api.assistant.resolve_target.v1'
    target: dict[str, Any] = Field(default_factory=dict)
    resolution_summary: str = ''
    required_permission: Optional[str] = None
    navigation_hints: list[dict[str, Any]] = Field(default_factory=list)
    detail_actions: list[dict[str, Any]] = Field(default_factory=list)
    source_lines: list[str] = Field(default_factory=list)
    fact: dict[str, Any] = Field(default_factory=dict)
    table: dict[str, Any] = Field(default_factory=dict)
    missing_data_request: dict[str, Any] = Field(default_factory=dict)


class SupportSummary(BaseModel):
    open_support_cases: int = 0
    open_incidents: int = 0
    critical_open_incidents: int = 0
    diagnostics_available: int = 0
    support_bundle_count: int = 0
    release_notes_total: int = 0


class SupportResponse(BaseModel):
    schema: str = 'genomeai.api.support.summary.v1'
    release: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)
    summary: SupportSummary = Field(default_factory=SupportSummary)
    source_paths: dict[str, Any] = Field(default_factory=dict)


class PilotPackItem(BaseModel):
    pack_id: str
    data_version: str
    created_at: Optional[str] = None
    status: str = 'ready'
    file_count: int = 0
    linkage: ApiLinkage = Field(default_factory=ApiLinkage)
    source_paths: dict[str, Any] = Field(default_factory=dict)


class PilotSummary(BaseModel):
    total_pilot_packs: int = 0
    latest_data_version: Optional[str] = None
    latest_pack_id: Optional[str] = None


class PilotResponse(BaseModel):
    schema: str = 'genomeai.api.pilot.summary.v1'
    summary: PilotSummary = Field(default_factory=PilotSummary)
    items: list[PilotPackItem] = Field(default_factory=list)


class InsightRecommendation(BaseModel):
    id: str
    text: str
    deadline: Optional[str] = None


class InsightItem(BaseModel):
    insight_id: str
    type: str
    severity: str
    status: str = 'to_check'
    date: str
    animal_ids: list[str] = Field(default_factory=list)
    title: str
    body: str
    action: str = ''
    tags: list[str] = Field(default_factory=list)
    farm_id: Optional[str] = None
    farm_label: Optional[str] = None
    farm_pct: Optional[float] = None
    holding_pct: Optional[float] = None
    chart_data: list[float] = Field(default_factory=list)
    chart_label: Optional[str] = None
    chart_unit: Optional[str] = None
    recommendations: list[InsightRecommendation] = Field(default_factory=list)
    edited_at: Optional[str] = None
    edited_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class InsightsListResponse(BaseModel):
    schema: str = 'genomeai.api.insights.list.v1'
    total: int = 0
    items: list[InsightItem] = Field(default_factory=list)


class InsightTransitionRequest(BaseModel):
    status: str


class InsightUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    action: Optional[str] = None
    recommendations: Optional[list[InsightRecommendation]] = None


class InsightSettings(BaseModel):
    schema: str = 'genomeai.api.insight_settings.v1'
    min_severity: str = 'info'
    enabled_categories: list[str] = Field(
        default_factory=lambda: [
            'production', 'reproduction', 'health',
            'feeding', 'welfare', 'economics',
        ]
    )


class ScanNowResponse(BaseModel):
    schema: str = 'genomeai.api.insights.scan_now.v1'
    count: int = 0
    insight_ids: list[str] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None


class ReadinessCheck(BaseModel):
    check_id: str
    status: str
    severity: str = 'info'
    message: str


class ReadinessSummary(BaseModel):
    overall_status: str = 'unknown'
    checks_total: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0


class ReadinessResponse(BaseModel):
    schema: str = 'genomeai.api.readiness.summary.v1'
    profile: Optional[str] = None
    summary: ReadinessSummary = Field(default_factory=ReadinessSummary)
    checks: list[ReadinessCheck] = Field(default_factory=list)
    source_paths: dict[str, Any] = Field(default_factory=dict)


class QcIncident(BaseModel):
    incident_id: str
    farm_id: str
    metric_id: str
    period_start: str
    period_end: Optional[str] = None
    detector_type: str
    severity: str = 'warn'
    affected_sensors: list[str] = Field(default_factory=list)
    ai_description: Optional[str] = None
    root_cause: Optional[str] = None
    status: str = 'active'
    detected_at: str


class QcIncidentsListResponse(BaseModel):
    schema: str = 'genomeai.api.qc.incidents.list.v1'
    total: int = 0
    items: list[QcIncident] = Field(default_factory=list)


class QcDismissResponse(BaseModel):
    schema: str = 'genomeai.api.qc.incidents.dismiss.v1'
    incident_id: str
    status: str


class UploadColumnSpec(BaseModel):
    name: str
    required: bool = True
    kind: str = 'str'
    description: str = ''
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    fk_table: Optional[str] = None


class UploadTypeMeta(BaseModel):
    schema: str = 'genomeai.api.uploads.type.v1'
    type: str
    label: str
    target_table: str
    instructions: str = ''
    columns: list[UploadColumnSpec] = Field(default_factory=list)


class UploadTypesListResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.types.list.v1'
    items: list[UploadTypeMeta] = Field(default_factory=list)


class UploadRowError(BaseModel):
    row: int
    field: Optional[str] = None
    message: str


class UploadPreviewResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.preview.v1'
    type: str
    total_rows: int = 0
    valid: int = 0
    duplicates: int = 0
    errors: list[UploadRowError] = Field(default_factory=list)
    preview_token: str = ''
    valid_rows_sample: list[dict[str, Any]] = Field(default_factory=list)


class UploadCommitRequest(BaseModel):
    preview_token: str


class UploadCommitResponse(BaseModel):
    schema: str = 'genomeai.api.uploads.commit.v1'
    inserted: int = 0
    skipped_duplicates: int = 0
