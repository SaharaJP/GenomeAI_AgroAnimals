from __future__ import annotations

from typing import Any, Optional

from core.domain import ApprovalStatus
from core.infra import ReportApprovalsRepo

from core.infra.web_db import utcnow_iso


def ensure_report_row(
    conn: Any,
    *,
    tenant_id: str,
    data_version: str,
    report_version: str,
) -> None:
    dv = (data_version or "").strip()
    rv = (report_version or "").strip()
    if not dv:
        raise ValueError("reports.data_version пуст")
    if not rv:
        raise ValueError("reports.report_version пуст")
    ReportApprovalsRepo(conn).ensure_row(tenant_id=tenant_id, data_version=dv, report_version=rv, now=utcnow_iso(), status=ApprovalStatus.DRAFT.value)


def get_report_approval(
    conn: Any,
    *,
    tenant_id: str,
    data_version: str,
    report_version: str,
) -> Optional[dict[str, Any]]:
    return ReportApprovalsRepo(conn).get(tenant_id=tenant_id, data_version=(data_version or "").strip(), report_version=(report_version or "").strip())


def list_report_statuses(
    conn: Any,
    *,
    tenant_id: str,
    data_version: str,
    report_versions: list[str],
) -> dict[str, dict[str, Any]]:
    dv = (data_version or "").strip()
    if not dv:
        return {rv: {"status": ApprovalStatus.DRAFT.value} for rv in report_versions}
    by_rv = ReportApprovalsRepo(conn).list_by_data_version(tenant_id=tenant_id, data_version=dv)
    out: dict[str, dict[str, Any]] = {}
    for rv in report_versions:
        out[rv] = by_rv.get(rv) or {"status": ApprovalStatus.DRAFT.value}
    return out


def approve_report(
    conn: Any,
    *,
    tenant_id: str,
    data_version: str,
    report_version: str,
    user_id: int,
    username: str,
    comment: str | None = None,
) -> dict[str, Any]:
    ensure_report_row(conn, tenant_id=tenant_id, data_version=data_version, report_version=report_version)
    repo = ReportApprovalsRepo(conn)
    before = repo.get(tenant_id=tenant_id, data_version=data_version, report_version=report_version) or {}
    repo.approve(
        tenant_id=tenant_id,
        data_version=(data_version or "").strip(),
        report_version=(report_version or "").strip(),
        updated_at=utcnow_iso(),
        user_id=int(user_id),
        username=str(username),
        comment=(comment.strip() if isinstance(comment, str) and comment.strip() else None),
    )
    after = repo.get(tenant_id=tenant_id, data_version=data_version, report_version=report_version) or {}
    return {"before": before, "after": after}


def reject_report(
    conn: Any,
    *,
    tenant_id: str,
    data_version: str,
    report_version: str,
    user_id: int,
    username: str,
    comment: str | None = None,
) -> dict[str, Any]:
    ensure_report_row(conn, tenant_id=tenant_id, data_version=data_version, report_version=report_version)
    repo = ReportApprovalsRepo(conn)
    before = repo.get(tenant_id=tenant_id, data_version=data_version, report_version=report_version) or {}
    repo.reject(
        tenant_id=tenant_id,
        data_version=(data_version or "").strip(),
        report_version=(report_version or "").strip(),
        updated_at=utcnow_iso(),
        user_id=int(user_id),
        username=str(username),
        comment=(comment.strip() if isinstance(comment, str) and comment.strip() else None),
    )
    after = repo.get(tenant_id=tenant_id, data_version=data_version, report_version=report_version) or {}
    return {"before": before, "after": after}


def archive_report(
    conn: Any,
    *,
    tenant_id: str,
    data_version: str,
    report_version: str,
    user_id: int,
    username: str,
    comment: str | None = None,
) -> dict[str, Any]:
    ensure_report_row(conn, tenant_id=tenant_id, data_version=data_version, report_version=report_version)
    repo = ReportApprovalsRepo(conn)
    before = repo.get(tenant_id=tenant_id, data_version=data_version, report_version=report_version) or {}
    repo.archive(
        tenant_id=tenant_id,
        data_version=(data_version or "").strip(),
        report_version=(report_version or "").strip(),
        updated_at=utcnow_iso(),
        user_id=int(user_id),
        username=str(username),
        comment=(comment.strip() if isinstance(comment, str) and comment.strip() else None),
    )
    after = repo.get(tenant_id=tenant_id, data_version=data_version, report_version=report_version) or {}
    return {"before": before, "after": after}
