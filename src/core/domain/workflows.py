from __future__ import annotations

from typing import Any

import pandas as pd

from core.domain.enums import (
    ALERT_OPEN_STATUSES,
    APPROVAL_STATUSES,
    DEFAULT_ACCEPTED_REASON_CODES,
    DEFAULT_REJECTED_REASON_CODES,
    TASK_ACTIVE_STATUSES,
    TASK_CLOSED_STATUSES,
    AlertStatus,
    ApprovalStatus,
    FeedbackDecision,
)
from core.domain.records import FeedbackConfig


FEEDBACK_DECISION_VALUES = frozenset({item.value for item in FeedbackDecision})


def normalize_feedback_decision(decision: str) -> str:
    return str(decision or "").strip().lower()


def reason_codes_for_feedback_decision(decision: str, cfg: FeedbackConfig) -> tuple[str, ...]:
    d = normalize_feedback_decision(decision)
    if d == FeedbackDecision.ACCEPTED.value:
        return tuple(cfg.accepted_codes or DEFAULT_ACCEPTED_REASON_CODES)
    if d == FeedbackDecision.REJECTED.value:
        return tuple(cfg.rejected_codes or DEFAULT_REJECTED_REASON_CODES)
    return tuple()


def validate_feedback_decision_and_reason(*, decision: str, reason_code: str, cfg: FeedbackConfig) -> None:
    d = normalize_feedback_decision(decision)
    if d not in FEEDBACK_DECISION_VALUES:
        raise ValueError("invalid_decision: expected accepted|rejected")
    rc = str(reason_code or "").strip()
    if not rc:
        raise ValueError("reason_code_required")
    allowed = set(reason_codes_for_feedback_decision(d, cfg))
    if allowed and rc not in allowed:
        raise ValueError(f"invalid_reason_code: expected one of {sorted(allowed)}, got {rc}")


def task_outcome_label_from_status(status: Any) -> Any:
    if status is None or pd.isna(status):
        return pd.NA
    st = str(status).strip().lower()
    if not st:
        return pd.NA
    if st in {"done", "closed", "resolved"}:
        return 1
    if st in (set(TASK_CLOSED_STATUSES) | {ApprovalStatus.ARCHIVED.value, FeedbackDecision.REJECTED.value}):
        return 0
    return pd.NA


def normalize_task_active_status_for_update(status: Any) -> str:
    st = str(status or "").strip()
    if st not in TASK_ACTIVE_STATUSES:
        raise ValueError(f"invalid_status_for_update: allowed open|in_progress, got {st}")
    return st


def normalize_task_close_status(status: Any) -> str:
    st = str(status or "").strip()
    if st not in TASK_CLOSED_STATUSES:
        raise ValueError("invalid_status")
    return st


def assert_alert_can_acknowledge(status: Any) -> str:
    st = str(status or "").strip().lower()
    if st == AlertStatus.RESOLVED.value:
        raise ValueError("already_resolved")
    return st


def alert_open_statuses_sql() -> str:
    return ",".join(repr(v) for v in sorted(ALERT_OPEN_STATUSES))


def require_draft_approval_status(
    status: Any,
    *,
    entity_label: str,
    action_label: str,
    forbidden_word: str = "запрещено",
) -> str:
    st = str(status or "").strip().lower()
    if st not in APPROVAL_STATUSES:
        raise ValueError(f"invalid_approval_status: expected one of {sorted(APPROVAL_STATUSES)}, got {status}")
    if st == ApprovalStatus.DRAFT.value:
        return st
    if st == ApprovalStatus.ARCHIVED.value:
        raise ValueError(f"{entity_label} в статусе archived: {action_label} {forbidden_word}")
    raise ValueError(f"{entity_label} не в статусе draft: {action_label} {forbidden_word}")


__all__ = [
    "FEEDBACK_DECISION_VALUES",
    "alert_open_statuses_sql",
    "assert_alert_can_acknowledge",
    "normalize_feedback_decision",
    "normalize_task_active_status_for_update",
    "normalize_task_close_status",
    "reason_codes_for_feedback_decision",
    "require_draft_approval_status",
    "task_outcome_label_from_status",
    "validate_feedback_decision_and_reason",
]
