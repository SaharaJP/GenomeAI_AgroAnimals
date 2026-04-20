from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.audit import aggregate_audit_facets, list_audit, write_audit
from core.infra.web_db import get_permissions_for_role, init_db
from core.security import (
    PermissionDenied,
    ROLE_ADMIN,
    ROLE_DIRECTOR,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    ROLE_VET,
    ROLE_ZOOTECH,
    ensure_permissions,
    permission_denied_detail,
    resolve_role_permissions,
)


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_DIRECTOR, ROLE_OPERATOR, ROLE_VIEWER, ROLE_VET, ROLE_ZOOTECH])
def test_t15_10_core_role_permissions_match_db_seed(role: str, tmp_path: Path) -> None:
    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        assert set(get_permissions_for_role(conn, role)) == set(resolve_role_permissions(role))
    finally:
        conn.close()


def test_t15_10_core_permission_denied_detail_is_human_readable() -> None:
    with pytest.raises(PermissionDenied) as exc_info:
        ensure_permissions(["kpi.view"], "audit.view", role="Viewer", operation="audit.page")
    detail = permission_denied_detail(exc_info.value)
    assert detail["error"] == "forbidden"
    assert detail["missing_permissions"] == ["audit.view"]
    assert detail["role"] == "Viewer"
    assert "audit.page" in str(exc_info.value)


def test_t15_10_core_audit_search_supports_prefix_role_request_and_object_ref(tmp_path: Path) -> None:
    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        write_audit(
            conn,
            tenant_id="default",
            user_id=1,
            username="director",
            role="Director",
            action="report.approve",
            object_type="report",
            object_id="rp_001",
            request_id="REQ-001",
            run_id="run_rp_001",
            status="OK",
        )
        write_audit(
            conn,
            tenant_id="default",
            user_id=2,
            username="operator",
            role="Operator",
            action="report.generate",
            object_type="report",
            object_id="rp_002",
            request_id="REQ-002",
            run_id="run_rp_002",
            status="OK",
        )

        rows = list_audit(
            conn,
            tenant_id="default",
            action_prefix="report.",
            role="Director",
            request_id="REQ-001",
            object_ref="report:rp_001",
        )
        assert len(rows) == 1
        assert rows[0]["action"] == "report.approve"
        assert rows[0]["object"]["ref"] == "report:rp_001"

        facets = aggregate_audit_facets(conn, tenant_id="default", action_prefix="report.")
        assert facets["summary"]["filtered_total"] == 2
        assert any(item["key"] == "approve" for item in facets["by_action_group"])
    finally:
        conn.close()
