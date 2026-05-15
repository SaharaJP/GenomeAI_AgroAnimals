from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Optional

from core.domain.enums import DEFAULT_ACCEPTED_REASON_CODES, DEFAULT_REJECTED_REASON_CODES


@dataclass(frozen=True)
class Personnel:
    personnel_id: str
    full_name: str
    position: str
    group_id: Optional[str] = None
    photo_ref: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    hired_at: Optional[str] = None
    user_id: Optional[int] = None
    tenant_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    PII_FIELDS: ClassVar[tuple[str, ...]] = ("phone", "email", "hired_at")

    def masked(self) -> "Personnel":
        return Personnel(
            personnel_id=self.personnel_id,
            full_name=self.full_name,
            position=self.position,
            group_id=self.group_id,
            photo_ref=self.photo_ref,
            phone=None,
            email=None,
            hired_at=None,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@dataclass
class AnimalEventCreate:
    animal_id: str
    event_type: str
    event_ts: str
    farm_id: Optional[str] = None
    site_id: Optional[str] = None
    lactation_id: Optional[str] = None
    actor_type: str = "unknown"
    actor_user_id: Optional[int] = None
    actor_username: Optional[str] = None
    source: str = "unknown"
    source_ref: Optional[str] = None
    reason_code: Optional[str] = None
    linked_object_type: Optional[str] = None
    linked_object_id: Optional[str] = None
    linked_decision_id: Optional[str] = None
    linked_task_id: Optional[str] = None
    request_id: Optional[str] = None
    job_id: Optional[str] = None
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    payload: dict[str, Any] | None = None
    event_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class FeedbackConfig:
    default_window_days: int = 30
    accepted_codes: tuple[str, ...] = DEFAULT_ACCEPTED_REASON_CODES
    rejected_codes: tuple[str, ...] = DEFAULT_REJECTED_REASON_CODES
    latency_buckets_hours: tuple[int, ...] = (4, 24, 72)
    default_sample_weight: float = 1.0
    sample_weight_by_reason: tuple[tuple[str, float], ...] = tuple()


@dataclass(frozen=True)
class QcIssue:
    qc_run: str
    data_version: str
    rule_id: str
    domain: str
    dataset: str
    severity: str
    message: str
    remediation: str
    row_id: Optional[str] = None
    field: Optional[str] = None
    sample_value: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "qc_run": self.qc_run,
            "data_version": self.data_version,
            "rule_id": self.rule_id,
            "domain": self.domain,
            "dataset": self.dataset,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation,
            "row_id": self.row_id,
            "field": self.field,
            "sample_value": self.sample_value,
        }


@dataclass(frozen=True)
class AutoAlert:
    alert_id: str
    tenant_id: str
    farm_id: str
    alert_date: str
    severity: str
    alert_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    message: str
    source_rule_id: str
    qc_run: str
    data_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "alert_id": self.alert_id,
            "farm_id": self.farm_id,
            "alert_date": self.alert_date,
            "severity": self.severity,
            "alert_type": self.alert_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "message": self.message,
            "source_rule_id": self.source_rule_id,
            "qc_run": self.qc_run,
            "data_version": self.data_version,
        }


@dataclass
class AlertCreate:
    alert_type: str
    title: str
    source: str
    cause: str
    confidence: Optional[float]
    object_type: str
    object_id: str
    deadline: Optional[str]
    owner_user_id: Optional[int]
    attachments: list[dict[str, Any]]
    why: dict[str, Any]
    what_to_do: list[dict[str, Any]]
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    dedupe_key: Optional[str] = None
    status: Optional[str] = None
    alert_id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Task:
    task_type: str
    title: str
    domain: Optional[str] = None
    priority: int = 3
    due_at: Optional[str] = None
    owner_user_id: Optional[int] = None
    assignee_team: Optional[str] = None
    stage: Optional[str] = None
    sla_hours: Optional[int] = None
    sla_source: Optional[str] = None
    related_alert: Optional[str] = None
    object_type: Optional[str] = None
    object_id: Optional[str] = None
    worklist_type: Optional[str] = None
    confidence: Optional[float] = None
    linked_decision_id: Optional[str] = None
    linked_task_id: Optional[str] = None
    linked_source_facts: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None
    why: dict[str, Any] | None = None
    what_to_do: list[dict[str, Any]] | None = None
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    dedupe_key: Optional[str] = None
    task_id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    status: Optional[str] = None
    closed_reason: Optional[str] = None
    closed_at: Optional[str] = None
    assigned_at: Optional[str] = None
    started_at: Optional[str] = None
    is_overdue: Optional[bool] = None
    latest_outcome_id: Optional[str] = None
    latest_outcome_status: Optional[str] = None
    latest_outcome_reason_code: Optional[str] = None
    latest_outcome_at: Optional[str] = None
    latest_outcome_by: Optional[int] = None
    latest_outcome_comment: Optional[str] = None
    outcome_metrics: dict[str, Any] | None = None
    source_insight_id: Optional[str] = None


TaskCreate = Task
Worklist = Task
WorklistCreate = Task


@dataclass
class CompletionOutcome:
    outcome_id: str
    tenant_id: str
    created_at: str
    outcome_status: str
    reason_code: str
    worklist_id: Optional[str] = None
    task_id: Optional[str] = None
    linked_decision_id: Optional[str] = None
    related_alert: Optional[str] = None
    object_type: Optional[str] = None
    object_id: Optional[str] = None
    owner_user_id: Optional[int] = None
    assignee_team: Optional[str] = None
    worklist_type: Optional[str] = None
    priority: Optional[int] = None
    confidence: Optional[float] = None
    due_at: Optional[str] = None
    outcome_by: Optional[int] = None
    outcome_by_username: Optional[str] = None
    outcome_role: Optional[str] = None
    comment: Optional[str] = None
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    request_id: Optional[str] = None
    metrics: dict[str, Any] | None = None
    auto_actions: dict[str, Any] | None = None

@dataclass
class DecisionRecord:
    schema: str
    created_at_utc: str
    user: str
    animal_id: str
    lactation_id: str
    recommendation_type: str
    decision: str
    comment: str
    lactation_no: Optional[int] = None
    farm_id: Optional[str] = None
    scoring_run: Optional[str] = None


@dataclass
class RunVersions:
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    decision_log: Optional[str] = None


@dataclass
class RunMeta:
    run_id: str
    created_at_utc: str
    tool: str = "genomeai"
    schema: str = "genomeai.run_metadata.v1"
    notes: Optional[str] = None


RunMetadata = RunMeta

__all__ = [
    "AlertCreate",
    "AnimalEventCreate",
    "AutoAlert",
    "CompletionOutcome",
    "DecisionRecord",
    "FeedbackConfig",
    "QcIssue",
    "RunMeta",
    "RunMetadata",
    "RunVersions",
    "Task",
    "TaskCreate",
    "Worklist",
    "WorklistCreate",
]
