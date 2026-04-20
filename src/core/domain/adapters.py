from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from core.domain.records import AlertCreate, DecisionRecord, RunMeta, Task


def _legacy_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_legacy_primitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_legacy_primitive(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _legacy_primitive(item) for key, item in value.items()}
    return value


def model_dump_compat(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        payload = dict(model.model_dump())
    elif hasattr(model, "dict"):
        payload = dict(model.dict())
    elif is_dataclass(model):
        payload = asdict(model)
    else:
        raise TypeError(f"Unsupported model type for dump: {type(model)!r}")
    return {str(key): _legacy_primitive(value) for key, value in payload.items()}


def canonical_model_to_legacy_dict(model: Any) -> dict[str, Any]:
    return model_dump_compat(model)


def run_meta_to_legacy_dict(meta: RunMeta) -> dict[str, Any]:
    return canonical_model_to_legacy_dict(meta)


run_metadata_to_legacy_dict = run_meta_to_legacy_dict


def decision_record_to_legacy_dict(record: DecisionRecord) -> dict[str, Any]:
    return canonical_model_to_legacy_dict(record)


def task_from_row(row: Mapping[str, Any]) -> Task:
    payload = dict(row)
    return Task(
        task_id=payload.get("task_id"),
        tenant_id=payload.get("tenant_id"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        task_type=str(payload.get("task_type") or ""),
        title=str(payload.get("title") or ""),
        domain=payload.get("domain"),
        priority=int(payload.get("priority") or 0) if payload.get("priority") is not None else 0,
        status=payload.get("status"),
        due_at=payload.get("due_at"),
        owner_user_id=(int(payload.get("owner_user_id")) if payload.get("owner_user_id") not in (None, "") else None),
        assignee_team=payload.get("assignee_team"),
        sla_hours=(int(payload.get("sla_hours")) if payload.get("sla_hours") not in (None, "") else None),
        sla_source=payload.get("sla_source"),
        stage=payload.get("stage"),
        related_alert=payload.get("related_alert"),
        object_type=payload.get("object_type"),
        object_id=payload.get("object_id"),
        worklist_type=payload.get("worklist_type"),
        confidence=(float(payload.get("confidence")) if payload.get("confidence") not in (None, "") else None),
        linked_decision_id=payload.get("linked_decision_id"),
        linked_task_id=payload.get("linked_task_id"),
        linked_source_facts=list(payload.get("linked_source_facts") or []),
        attachments=list(payload.get("attachments") or []),
        why=dict(payload.get("why") or {}),
        what_to_do=list(payload.get("what_to_do") or []),
        data_version=payload.get("data_version"),
        qc_run=payload.get("qc_run"),
        model_version=payload.get("model_version"),
        scoring_run=payload.get("scoring_run"),
        report_version=payload.get("report_version"),
        dedupe_key=payload.get("dedupe_key"),
        closed_reason=payload.get("closed_reason"),
        closed_at=payload.get("closed_at"),
        assigned_at=payload.get("assigned_at"),
        started_at=payload.get("started_at"),
        is_overdue=payload.get("is_overdue"),
        latest_outcome_id=payload.get("latest_outcome_id"),
        latest_outcome_status=payload.get("latest_outcome_status"),
        latest_outcome_reason_code=payload.get("latest_outcome_reason_code"),
        latest_outcome_at=payload.get("latest_outcome_at"),
        latest_outcome_by=(int(payload.get("latest_outcome_by")) if payload.get("latest_outcome_by") not in (None, "") else None),
        latest_outcome_comment=payload.get("latest_outcome_comment"),
        outcome_metrics=dict(payload.get("outcome_metrics") or {}),
    )


def task_to_api_dict(task: Task) -> dict[str, Any]:
    payload = canonical_model_to_legacy_dict(task)
    payload["attachments"] = list(task.attachments or [])
    payload["linked_source_facts"] = list(task.linked_source_facts or [])
    payload["why"] = dict(task.why or {})
    payload["what_to_do"] = list(task.what_to_do or [])
    return payload


def alert_create_to_api_dict(alert: AlertCreate) -> dict[str, Any]:
    payload = canonical_model_to_legacy_dict(alert)
    payload["attachments"] = list(alert.attachments or [])
    payload["why"] = dict(alert.why or {})
    payload["what_to_do"] = list(alert.what_to_do or [])
    return payload


__all__ = [
    "alert_create_to_api_dict",
    "canonical_model_to_legacy_dict",
    "decision_record_to_legacy_dict",
    "model_dump_compat",
    "run_meta_to_legacy_dict",
    "run_metadata_to_legacy_dict",
    "task_from_row",
    "task_to_api_dict",
]
