from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from core.infra import WhatIfReportsRepo

from core.infra.web_db import utcnow_iso


@dataclass
class WhatIfReportCreate:
    scenario_id: str
    report_version: str
    data_version: str
    base_economics_run: str
    scenario_economics_run: str
    pdf_rel_path: str
    params: dict[str, Any] | None = None


def create_report(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    r: WhatIfReportCreate,
) -> None:
    WhatIfReportsRepo(conn).create(
        tenant_id=tenant_id,
        created_at=utcnow_iso(),
        created_by=int(user_id),
        created_by_username=str(username),
        scenario_id=str(r.scenario_id),
        report_version=str(r.report_version),
        data_version=str(r.data_version),
        base_economics_run=str(r.base_economics_run),
        scenario_economics_run=str(r.scenario_economics_run),
        pdf_rel_path=str(r.pdf_rel_path),
        params=(r.params or {}),
    )


def get_report(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    report_version: str,
) -> Optional[dict[str, Any]]:
    return WhatIfReportsRepo(conn).get(tenant_id=tenant_id, report_version=report_version)


def list_reports(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    scenario_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return WhatIfReportsRepo(conn).list(tenant_id=tenant_id, scenario_id=scenario_id, limit=int(limit), offset=int(offset))
