from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any, Optional

from core.domain import ALERT_STATUSES, TASK_ACTIVE_STATUSES, TASK_CLOSED_STATUSES, TASK_STATUSES, WORKLIST_OUTCOME_STATUSES, normalize_task_close_status


WORKFLOW_DOMAINS = frozenset({"health", "repro", "data", "qc", "econ"})


def workflow_project_root() -> Path:
    return Path(os.environ.get("GENOMEAI_PROJECT_ROOT", Path(__file__).resolve().parents[3])).resolve()


@lru_cache(maxsize=16)
def load_workflow_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def utcnow_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def normalize_domain(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).strip().lower()
    if normalized in WORKFLOW_DOMAINS:
        return normalized
    return None


def normalize_priority(value: Any, *, default: int = 3) -> int:
    if value is None or value == "":
        return int(default)
    try:
        priority = int(value)
    except Exception as exc:
        raise ValueError(f"invalid_priority: expected int 1..5, got {value}") from exc
    if priority < 1 or priority > 5:
        raise ValueError(f"invalid_priority: must be 1..5, got {priority}")
    return priority


@lru_cache(maxsize=16)
def _load_sla_cfg() -> dict[str, Any]:
    return load_workflow_yaml(workflow_project_root() / "configs" / "workflow_v2" / "sla.yaml")


@lru_cache(maxsize=16)
def _load_reason_codes_cfg() -> dict[str, Any]:
    return load_workflow_yaml(workflow_project_root() / "configs" / "workflow_v2" / "reason_codes.yaml")


def pick_sla_hours(domain: str, priority: int) -> Optional[int]:
    cfg = _load_sla_cfg()
    dom = normalize_domain(domain) or normalize_domain(cfg.get("default_domain")) or "data"
    pr = normalize_priority(priority)
    try:
        return int((((cfg.get("domains") or {}).get(dom) or {}).get("priority_to_hours") or {}).get(pr))
    except Exception:
        return None


def derive_due_fields(
    *,
    due_at: Optional[str],
    sla_hours: Optional[int],
    domain: str,
    priority: int,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Centralize due_at/SLA derivation without changing legacy behavior."""

    ref_now = now or utcnow_dt()
    due_clean = (str(due_at).strip() if due_at else None)
    hours = (int(sla_hours) if sla_hours is not None else None)
    source: Optional[str] = None

    if not due_clean:
        if hours is None:
            hours = pick_sla_hours(domain, priority)
            if hours is not None:
                source = "cfg.default"
        if hours is not None:
            due_clean = (ref_now + timedelta(hours=int(hours))).isoformat()
            source = source or "cfg.default"
    else:
        if hours is None:
            due_dt = parse_iso_dt(due_clean)
            if due_dt is not None:
                diff_hours = max(0.0, (due_dt - ref_now).total_seconds() / 3600.0)
                hours = int(ceil(diff_hours))
                source = "derived.from_due_at"
        source = source or "user.due_at"

    return {
        "due_at": due_clean,
        "sla_hours": (int(hours) if hours is not None else None),
        "sla_source": source,
    }


def is_task_overdue(task: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    try:
        if str(task.get("status") or "") in TASK_CLOSED_STATUSES:
            return False
        due_dt = parse_iso_dt(task.get("due_at"))
        if not due_dt:
            return False
        return due_dt < (now or utcnow_dt())
    except Exception:
        return False


def workflow_domain_options() -> tuple[str, ...]:
    return tuple(sorted(WORKFLOW_DOMAINS))


def task_priority_options() -> tuple[int, ...]:
    return (1, 2, 3, 4, 5)


def alert_status_options() -> tuple[str, ...]:
    return tuple(sorted(ALERT_STATUSES))


def task_status_options() -> tuple[str, ...]:
    return tuple(sorted(TASK_STATUSES))


def task_active_status_options() -> tuple[str, ...]:
    return tuple(sorted(TASK_ACTIVE_STATUSES))


def task_close_status_options() -> tuple[str, ...]:
    return tuple(sorted(TASK_CLOSED_STATUSES))


def alert_resolve_reason_codes() -> tuple[str, ...]:
    cfg = _load_reason_codes_cfg()
    values = cfg.get("alert_resolve") or []
    return tuple(str(item).strip() for item in values if str(item).strip())


def task_close_reason_codes(*, status: Optional[str] = None) -> tuple[str, ...]:
    cfg = _load_reason_codes_cfg()
    task_cfg = dict(cfg.get("task_close") or {})
    default_codes = tuple(str(item).strip() for item in (task_cfg.get("default") or []) if str(item).strip())
    st = str(status or "").strip()
    if not st:
        return default_codes
    codes = task_cfg.get(st)
    if isinstance(codes, list) and codes:
        return tuple(str(item).strip() for item in codes if str(item).strip())
    return default_codes


def validate_reason_for_alert_resolution(reason: str) -> str:
    normalized = str(reason or "").strip()
    if not normalized:
        raise ValueError("reason_required")
    # Backward-compatible: free text is still allowed.
    return normalized




def completion_outcome_status_options() -> tuple[str, ...]:
    return tuple(sorted(WORKLIST_OUTCOME_STATUSES))


def completion_outcome_reason_codes(*, outcome_status: Optional[str] = None) -> tuple[str, ...]:
    cfg = _load_reason_codes_cfg()
    out_cfg = dict(cfg.get("completion_outcome") or {})
    default_codes = tuple(str(item).strip() for item in (out_cfg.get("default") or []) if str(item).strip())
    st = str(outcome_status or "").strip()
    if not st:
        return default_codes
    codes = out_cfg.get(st)
    if isinstance(codes, list) and codes:
        return tuple(str(item).strip() for item in codes if str(item).strip())
    return default_codes


def validate_reason_for_completion_outcome(*, outcome_status: str, reason_code: str) -> str:
    st = str(outcome_status or "").strip()
    if st not in WORKLIST_OUTCOME_STATUSES:
        raise ValueError(f"invalid_outcome_status: expected one of {sorted(WORKLIST_OUTCOME_STATUSES)}, got {outcome_status}")
    normalized = str(reason_code or "").strip()
    if not normalized:
        raise ValueError("reason_required")
    return normalized

def validate_reason_for_task_close(*, status: str, reason: str) -> str:
    normalize_task_close_status(status)
    normalized = str(reason or "").strip()
    if not normalized:
        raise ValueError("reason_required")
    # Backward-compatible: configured codes are hints/options, not a hard restriction.
    return normalized


__all__ = [
    "WORKFLOW_DOMAINS",
    "alert_resolve_reason_codes",
    "alert_status_options",
    "completion_outcome_reason_codes",
    "completion_outcome_status_options",
    "derive_due_fields",
    "is_task_overdue",
    "load_workflow_yaml",
    "normalize_domain",
    "normalize_priority",
    "parse_iso_dt",
    "pick_sla_hours",
    "task_active_status_options",
    "task_close_reason_codes",
    "task_close_status_options",
    "task_priority_options",
    "task_status_options",
    "workflow_domain_options",
    "utcnow_dt",
    "validate_reason_for_alert_resolution",
    "validate_reason_for_completion_outcome",
    "validate_reason_for_task_close",
    "workflow_project_root",
]
