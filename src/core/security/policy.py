from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# ---- Permissions catalog (Target) ----

PERM_KPI_VIEW = "kpi.view"
PERM_DRILLDOWN_VIEW = "drilldown.view"
PERM_UPLOAD_CREATE = "upload.create"
PERM_PIPELINE_RUN = "pipeline.run"
PERM_EXPORT_DOWNLOAD = "export.download"
# Legacy permission (MVP). Keep for backward compatibility.
PERM_ALERTS_CLOSE = "alerts.close"

# Alert Center v2 permissions
PERM_USERS_MANAGE = "users.manage"
PERM_ALERTS_VIEW = "alerts.view"
PERM_ALERTS_ACK = "alerts.ack"
PERM_ALERTS_RESOLVE = "alerts.resolve"
PERM_ALERTS_GENERATE = "alerts.generate"
PERM_ALERTS_CREATE = "alerts.create"  # manual alert
PERM_RECS_CONFIRM = "recommendations.confirm"
PERM_CONFIGS_MANAGE = "configs.manage"
PERM_AUDIT_VIEW = "audit.view"
PERM_DECISIONS_WRITE = "decisions.write"

# Decision Log v2 permissions
PERM_DECISIONLOG_VIEW = "decisionlog.view"
PERM_DECISIONLOG_WRITE = "decisionlog.write"

# Worklists / Tasks v1 permissions
PERM_TASKS_VIEW = "tasks.view"
PERM_TASKS_WRITE = "tasks.write"      # create/edit fields (owner/due/priority)
PERM_TASKS_CLOSE = "tasks.close"      # mark done/cancel
PERM_TASKS_GENERATE = "tasks.generate"  # auto-create from alerts/rules

# --- Personalization (T10-04) ---
PERM_SAVED_VIEWS_VIEW = "saved_views.view"
PERM_SAVED_VIEWS_WRITE = "saved_views.write"
PERM_TEMPLATES_VIEW = "report_templates.view"
PERM_TEMPLATES_WRITE = "report_templates.write"
PERM_TEMPLATES_GENERATE = "report_templates.generate"
PERM_FAVORITES_VIEW = "favorites.view"
PERM_FAVORITES_WRITE = "favorites.write"

# --- T20-02 Operational animal events quick entry ---
PERM_ANIMAL_EVENTS_VIEW = "animal_events.view"
PERM_ANIMAL_EVENTS_WRITE = "animal_events.write"
PERM_ANIMAL_EVENTS_CONFIRM = "animal_events.confirm"
PERM_ANIMAL_EVENTS_CLOSE = "animal_events.close"

# --- Economics 2.0 (T11-01) ---
PERM_ECONOMICS_VIEW = "economics.view"

# --- What-If 2.0 scenarios (T11-04) ---
PERM_WHATIF_SCENARIOS_VIEW = "whatif.scenarios.view"
PERM_WHATIF_SCENARIOS_WRITE = "whatif.scenarios.write"
PERM_WHATIF_SCENARIOS_APPROVE = "whatif.scenarios.approve"
PERM_WHATIF_SCENARIOS_CLONE = "whatif.scenarios.clone"
PERM_WHATIF_SCENARIOS_ARCHIVE = "whatif.scenarios.archive"

# --- What-If 2.0 reports (T11-04) ---
PERM_WHATIF_REPORT_VIEW = "whatif.report.view"
PERM_WHATIF_REPORT_GENERATE = "whatif.report.generate"

# --- T12-03 Playbooks (action checklists) ---
PERM_PLAYBOOKS_VIEW = "playbooks.view"
PERM_PLAYBOOKS_WRITE = "playbooks.write"

# --- T12-04 Approvals / Weekly Plans ---
PERM_WEEKLY_PLANS_VIEW = "weekly_plans.view"
PERM_WEEKLY_PLANS_WRITE = "weekly_plans.write"
PERM_WEEKLY_PLANS_APPROVE = "weekly_plans.approve"
PERM_WEEKLY_PLANS_ARCHIVE = "weekly_plans.archive"

# --- T12-04 Approvals / Reports ---
PERM_REPORTS_VIEW = "reports.view"
PERM_REPORTS_APPROVE = "reports.approve"
PERM_REPORTS_ARCHIVE = "reports.archive"

# --- T28-04 External collaboration boundaries ---
PERM_COLLAB_COMMENTS_WRITE = "collaboration.comments.write"
PERM_COLLAB_RECOMMENDATIONS_WRITE = "collaboration.recommendations.write"
PERM_COLLAB_APPROVAL_REQUEST = "collaboration.approvals.request"
PERM_COLLAB_APPROVAL_REVIEW = "collaboration.approvals.review"

ALL_PERMISSIONS: list[str] = [
    PERM_KPI_VIEW,
    PERM_DRILLDOWN_VIEW,
    PERM_UPLOAD_CREATE,
    PERM_PIPELINE_RUN,
    PERM_EXPORT_DOWNLOAD,
    PERM_USERS_MANAGE,
    PERM_ALERTS_CLOSE,
    PERM_ALERTS_VIEW,
    PERM_ALERTS_ACK,
    PERM_ALERTS_RESOLVE,
    PERM_ALERTS_GENERATE,
    PERM_ALERTS_CREATE,
    PERM_RECS_CONFIRM,
    PERM_CONFIGS_MANAGE,
    PERM_AUDIT_VIEW,
    PERM_DECISIONS_WRITE,
    PERM_DECISIONLOG_VIEW,
    PERM_DECISIONLOG_WRITE,
    PERM_TASKS_VIEW,
    PERM_TASKS_WRITE,
    PERM_TASKS_CLOSE,
    PERM_TASKS_GENERATE,

    # T10-04
    PERM_SAVED_VIEWS_VIEW,
    PERM_SAVED_VIEWS_WRITE,
    PERM_TEMPLATES_VIEW,
    PERM_TEMPLATES_WRITE,
    PERM_TEMPLATES_GENERATE,
    PERM_FAVORITES_VIEW,
    PERM_FAVORITES_WRITE,

    # T20-02
    PERM_ANIMAL_EVENTS_VIEW,
    PERM_ANIMAL_EVENTS_WRITE,
    PERM_ANIMAL_EVENTS_CONFIRM,
    PERM_ANIMAL_EVENTS_CLOSE,

    # T11-01
    PERM_ECONOMICS_VIEW,

    # T11-04
    PERM_WHATIF_SCENARIOS_VIEW,
    PERM_WHATIF_SCENARIOS_WRITE,
    PERM_WHATIF_SCENARIOS_APPROVE,
    PERM_WHATIF_SCENARIOS_CLONE,
    PERM_WHATIF_SCENARIOS_ARCHIVE,
    PERM_WHATIF_REPORT_VIEW,
    PERM_WHATIF_REPORT_GENERATE,

    # T12-03
    PERM_PLAYBOOKS_VIEW,
    PERM_PLAYBOOKS_WRITE,

    # T12-04
    PERM_WEEKLY_PLANS_VIEW,
    PERM_WEEKLY_PLANS_WRITE,
    PERM_WEEKLY_PLANS_APPROVE,
    PERM_WEEKLY_PLANS_ARCHIVE,

    PERM_REPORTS_VIEW,
    PERM_REPORTS_APPROVE,
    PERM_REPORTS_ARCHIVE,

    # T28-04
    PERM_COLLAB_COMMENTS_WRITE,
    PERM_COLLAB_RECOMMENDATIONS_WRITE,
    PERM_COLLAB_APPROVAL_REQUEST,
    PERM_COLLAB_APPROVAL_REVIEW,
]

# ---- Role catalog ----
ROLE_ADMIN = "Admin"
ROLE_DIRECTOR = "Director"
ROLE_ZOOTECH = "Zootech"
ROLE_VET = "Vet"
ROLE_OPERATOR = "Operator"
ROLE_VIEWER = "Viewer"
ROLE_CONSULTANT = "Consultant"
ROLE_PARTNER = "Partner"

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_DIRECTOR: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_EXPORT_DOWNLOAD,
        # Director can set KPI goals/thresholds for plan-fact dashboards (T10-02)
        PERM_CONFIGS_MANAGE,
        # Alert Center v2
        PERM_ALERTS_VIEW,
        PERM_ALERTS_ACK,
        PERM_ALERTS_RESOLVE,
        # legacy
        PERM_ALERTS_CLOSE,
        PERM_RECS_CONFIRM,
        PERM_DECISIONS_WRITE,
        PERM_DECISIONLOG_VIEW,
        PERM_TASKS_VIEW,
        PERM_AUDIT_VIEW,

        # T10-04 personalization
        PERM_SAVED_VIEWS_VIEW,
        PERM_SAVED_VIEWS_WRITE,
        PERM_TEMPLATES_VIEW,
        PERM_TEMPLATES_WRITE,
        PERM_TEMPLATES_GENERATE,
        PERM_FAVORITES_VIEW,
        PERM_FAVORITES_WRITE,

        # T20-02
        PERM_ANIMAL_EVENTS_VIEW,

        # T11-01
        PERM_ECONOMICS_VIEW,

        # T11-04
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_SCENARIOS_WRITE,
        PERM_WHATIF_SCENARIOS_APPROVE,
        PERM_WHATIF_SCENARIOS_CLONE,
        PERM_WHATIF_SCENARIOS_ARCHIVE,
        PERM_WHATIF_REPORT_VIEW,
        PERM_WHATIF_REPORT_GENERATE,

        # T12-03 playbooks
        PERM_PLAYBOOKS_VIEW,
        PERM_PLAYBOOKS_WRITE,

        # T12-04 weekly plans / approvals
        PERM_WEEKLY_PLANS_VIEW,
        PERM_WEEKLY_PLANS_WRITE,
        PERM_WEEKLY_PLANS_APPROVE,
        PERM_WEEKLY_PLANS_ARCHIVE,

        # T12-04 report approvals
        PERM_REPORTS_VIEW,
        PERM_REPORTS_APPROVE,
        PERM_REPORTS_ARCHIVE,

        # T28-04 collaboration review
        PERM_COLLAB_COMMENTS_WRITE,
        PERM_COLLAB_RECOMMENDATIONS_WRITE,
        PERM_COLLAB_APPROVAL_REQUEST,
        PERM_COLLAB_APPROVAL_REVIEW,
    ],
    ROLE_ZOOTECH: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_UPLOAD_CREATE,
        PERM_PIPELINE_RUN,
        PERM_EXPORT_DOWNLOAD,
        # Alert Center v2
        PERM_ALERTS_VIEW,
        PERM_ALERTS_ACK,
        PERM_ALERTS_RESOLVE,
        PERM_ALERTS_GENERATE,
        # legacy
        PERM_ALERTS_CLOSE,
        PERM_RECS_CONFIRM,
        PERM_DECISIONS_WRITE,
        PERM_DECISIONLOG_VIEW,
        PERM_DECISIONLOG_WRITE,
        PERM_TASKS_VIEW,
        PERM_TASKS_WRITE,
        PERM_TASKS_CLOSE,
        PERM_TASKS_GENERATE,

        # T10-04
        PERM_SAVED_VIEWS_VIEW,
        PERM_SAVED_VIEWS_WRITE,
        PERM_TEMPLATES_VIEW,
        PERM_TEMPLATES_WRITE,
        PERM_TEMPLATES_GENERATE,
        PERM_FAVORITES_VIEW,
        PERM_FAVORITES_WRITE,

        # T20-02
        PERM_ANIMAL_EVENTS_VIEW,
        PERM_ANIMAL_EVENTS_WRITE,
        PERM_ANIMAL_EVENTS_CONFIRM,
        PERM_ANIMAL_EVENTS_CLOSE,

        # T11-01
        PERM_ECONOMICS_VIEW,

        # T11-04
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_SCENARIOS_WRITE,
        PERM_WHATIF_SCENARIOS_CLONE,
        PERM_WHATIF_REPORT_VIEW,
        PERM_WHATIF_REPORT_GENERATE,

        # T12-03 playbooks
        PERM_PLAYBOOKS_VIEW,
        PERM_PLAYBOOKS_WRITE,

        # T12-04 weekly plans (drafting)
        PERM_WEEKLY_PLANS_VIEW,
        PERM_WEEKLY_PLANS_WRITE,

        # T12-04 reports (read)
        PERM_REPORTS_VIEW,
    ],
    ROLE_VET: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_EXPORT_DOWNLOAD,
        # Alert Center v2
        PERM_ALERTS_VIEW,
        PERM_ALERTS_ACK,
        PERM_ALERTS_RESOLVE,
        PERM_ALERTS_GENERATE,
        # legacy
        PERM_ALERTS_CLOSE,
        PERM_DECISIONS_WRITE,
        PERM_DECISIONLOG_VIEW,
        PERM_DECISIONLOG_WRITE,
        PERM_TASKS_VIEW,
        PERM_TASKS_WRITE,
        PERM_TASKS_CLOSE,
        PERM_TASKS_GENERATE,

        # T10-04
        PERM_SAVED_VIEWS_VIEW,
        PERM_SAVED_VIEWS_WRITE,
        PERM_TEMPLATES_VIEW,
        PERM_TEMPLATES_WRITE,
        PERM_TEMPLATES_GENERATE,
        PERM_FAVORITES_VIEW,
        PERM_FAVORITES_WRITE,

        # T20-02
        PERM_ANIMAL_EVENTS_VIEW,
        PERM_ANIMAL_EVENTS_WRITE,
        PERM_ANIMAL_EVENTS_CONFIRM,
        PERM_ANIMAL_EVENTS_CLOSE,

        # T11-01
        PERM_ECONOMICS_VIEW,

        # T11-04
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_REPORT_VIEW,

        # T12-03 playbooks
        PERM_PLAYBOOKS_VIEW,
        PERM_PLAYBOOKS_WRITE,

        # T12-04 weekly plans (read)
        PERM_WEEKLY_PLANS_VIEW,

        # T12-04 reports (read)
        PERM_REPORTS_VIEW,
    ],
    ROLE_OPERATOR: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_UPLOAD_CREATE,
        PERM_PIPELINE_RUN,
        PERM_EXPORT_DOWNLOAD,
        # Alert Center v2
        PERM_ALERTS_VIEW,
        PERM_DECISIONS_WRITE,
        PERM_DECISIONLOG_VIEW,
        PERM_DECISIONLOG_WRITE,
        PERM_TASKS_VIEW,
        PERM_TASKS_CLOSE,

        # T10-04 (operator can save views/favorites; templates are read-only)
        PERM_SAVED_VIEWS_VIEW,
        PERM_SAVED_VIEWS_WRITE,
        PERM_TEMPLATES_VIEW,
        PERM_FAVORITES_VIEW,
        PERM_FAVORITES_WRITE,

        # T20-02
        PERM_ANIMAL_EVENTS_VIEW,
        PERM_ANIMAL_EVENTS_WRITE,
        PERM_ANIMAL_EVENTS_CONFIRM,
        PERM_ANIMAL_EVENTS_CLOSE,

        # T11-01
        PERM_ECONOMICS_VIEW,

        # T11-04
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_SCENARIOS_WRITE,
        PERM_WHATIF_SCENARIOS_CLONE,
        PERM_WHATIF_REPORT_VIEW,
        PERM_WHATIF_REPORT_GENERATE,

        # T12-03 playbooks (read-only)
        PERM_PLAYBOOKS_VIEW,

        # T12-04 weekly plans (read)
        PERM_WEEKLY_PLANS_VIEW,

        # T12-04 reports (read)
        PERM_REPORTS_VIEW,
    ],
    ROLE_VIEWER: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_EXPORT_DOWNLOAD,
        # Alert Center v2 (read-only)
        PERM_ALERTS_VIEW,
        PERM_DECISIONLOG_VIEW,
        PERM_TASKS_VIEW,

        # T10-04 (viewer can manage own views/favorites)
        PERM_SAVED_VIEWS_VIEW,
        PERM_SAVED_VIEWS_WRITE,
        PERM_FAVORITES_VIEW,
        PERM_FAVORITES_WRITE,

        # T20-02
        PERM_ANIMAL_EVENTS_VIEW,

        # T11-01
        PERM_ECONOMICS_VIEW,

        # T11-04 (read-only)
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_REPORT_VIEW,

        # T12-03 playbooks (read-only)
        PERM_PLAYBOOKS_VIEW,

        # T12-04 weekly plans (read)
        PERM_WEEKLY_PLANS_VIEW,

        # T12-04 reports (read)
        PERM_REPORTS_VIEW,
    ],
    ROLE_CONSULTANT: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_TASKS_VIEW,
        PERM_DECISIONLOG_VIEW,
        PERM_ALERTS_VIEW,
        PERM_REPORTS_VIEW,
        PERM_WEEKLY_PLANS_VIEW,
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_REPORT_VIEW,
        PERM_PLAYBOOKS_VIEW,
        PERM_SAVED_VIEWS_VIEW,
        PERM_FAVORITES_VIEW,
        PERM_COLLAB_COMMENTS_WRITE,
        PERM_COLLAB_RECOMMENDATIONS_WRITE,
        PERM_COLLAB_APPROVAL_REQUEST,
    ],
    ROLE_PARTNER: [
        PERM_KPI_VIEW,
        PERM_DRILLDOWN_VIEW,
        PERM_TASKS_VIEW,
        PERM_DECISIONLOG_VIEW,
        PERM_ALERTS_VIEW,
        PERM_REPORTS_VIEW,
        PERM_WEEKLY_PLANS_VIEW,
        PERM_WHATIF_SCENARIOS_VIEW,
        PERM_WHATIF_REPORT_VIEW,
        PERM_PLAYBOOKS_VIEW,
        PERM_SAVED_VIEWS_VIEW,
        PERM_FAVORITES_VIEW,
        PERM_COLLAB_COMMENTS_WRITE,
        PERM_COLLAB_RECOMMENDATIONS_WRITE,
        PERM_COLLAB_APPROVAL_REQUEST,
    ],
}

# Backwards-compatible alias used by Streamlit cabinet.
# (Earlier versions referenced ROLE_PERMISSIONS; keep it stable.)
ROLE_PERMISSIONS = DEFAULT_ROLE_PERMISSIONS



@dataclass(slots=True)
class PermissionDenied(Exception):
    missing_permissions: tuple[str, ...]
    role: str | None = None
    operation: str | None = None

    def __str__(self) -> str:
        missing = ', '.join(self.missing_permissions) or 'unknown'
        prefix = f"Недостаточно прав для {self.operation}: " if self.operation else "Недостаточно прав: "
        role_suffix = f" (role={self.role})" if self.role else ""
        return prefix + missing + role_suffix


@dataclass(slots=True)
class RoleDenied(Exception):
    role: str
    allowed_roles: tuple[str, ...]

    def __str__(self) -> str:
        allowed = ', '.join(self.allowed_roles) or 'none'
        return f"Недостаточно прав: роль '{self.role}' не допускается. Требуется: {allowed}"


def map_legacy_role(role: str) -> str:
    r = (role or '').lower()
    if r == 'admin':
        return ROLE_ADMIN
    if r == 'operator':
        return ROLE_OPERATOR
    if r == 'viewer':
        return ROLE_VIEWER
    return role


def normalize_permissions(permissions: Iterable[str] | None) -> tuple[str, ...]:
    values = []
    seen: set[str] = set()
    for raw in permissions or ():
        value = str(raw or '').strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return tuple(values)


def resolve_role_permissions(role: str, *, role_permissions: Mapping[str, Sequence[str]] | None = None) -> tuple[str, ...]:
    catalog = role_permissions or DEFAULT_ROLE_PERMISSIONS
    canonical_role = map_legacy_role(str(role or ''))
    return normalize_permissions(catalog.get(canonical_role, ()))


def merge_permissions(*groups: Iterable[str] | None) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in normalize_permissions(group):
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return tuple(merged)


def missing_permissions(user_permissions: Iterable[str] | None, required_permissions: Iterable[str] | None) -> tuple[str, ...]:
    perms = set(normalize_permissions(user_permissions))
    required = normalize_permissions(required_permissions)
    return tuple(p for p in required if p not in perms)


def has_all_permissions(user_permissions: Iterable[str] | None, *required_permissions: str) -> bool:
    return not missing_permissions(user_permissions, required_permissions)


def has_any_permission(user_permissions: Iterable[str] | None, *required_permissions: str) -> bool:
    perms = set(normalize_permissions(user_permissions))
    required = normalize_permissions(required_permissions)
    return not required or any(p in perms for p in required)


def ensure_permissions(
    user_permissions: Iterable[str] | None,
    *required_permissions: str,
    role: str | None = None,
    operation: str | None = None,
) -> tuple[str, ...]:
    missing = missing_permissions(user_permissions, required_permissions)
    if missing:
        raise PermissionDenied(missing_permissions=missing, role=role, operation=operation)
    return normalize_permissions(user_permissions)


def ensure_any_permission(
    user_permissions: Iterable[str] | None,
    *required_permissions: str,
    role: str | None = None,
    operation: str | None = None,
) -> tuple[str, ...]:
    perms = normalize_permissions(user_permissions)
    if required_permissions and not has_any_permission(perms, *required_permissions):
        raise PermissionDenied(missing_permissions=normalize_permissions(required_permissions), role=role, operation=operation)
    return perms


def ensure_role(role: str | None, *allowed_roles: str) -> str:
    canonical_role = map_legacy_role(str(role or ''))
    if allowed_roles and canonical_role not in set(allowed_roles):
        raise RoleDenied(role=canonical_role, allowed_roles=tuple(allowed_roles))
    return canonical_role


def permission_denied_detail(exc: PermissionDenied) -> dict[str, object]:
    return {
        'error': 'forbidden',
        'detail': str(exc),
        'missing_permissions': list(exc.missing_permissions),
        'role': exc.role,
        'operation': exc.operation,
    }


__all__ = [
    *(name for name in globals() if name.isupper()),
    'PermissionDenied',
    'RoleDenied',
    'ensure_any_permission',
    'ensure_permissions',
    'ensure_role',
    'has_all_permissions',
    'has_any_permission',
    'map_legacy_role',
    'merge_permissions',
    'missing_permissions',
    'normalize_permissions',
    'permission_denied_detail',
    'resolve_role_permissions',
]
