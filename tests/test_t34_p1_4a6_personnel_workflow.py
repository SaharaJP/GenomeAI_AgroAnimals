"""P1-4a-6: workflow + endpoint smoke for /personnel.

Unit-tests the pure logic in core.workflow.personnel and verifies
that the FastAPI routes are registered with the correct prefix.
Full end-to-end POST→GET runs against the live backend in the
execution proof (manual smoke).
"""
from __future__ import annotations

import re
from typing import Any

from core.domain.records import Personnel as DomainPersonnel
from core.workflow.personnel import (
    generate_personnel_id,
    row_to_personnel,
    utcnow_iso,
)


# ---------- generate_personnel_id ----------


def test_generate_personnel_id_prefix_and_length() -> None:
    pid = generate_personnel_id()
    assert pid.startswith("prsn_")
    assert re.fullmatch(r"prsn_[0-9a-f]{12}", pid) is not None


def test_generate_personnel_id_is_unique_per_call() -> None:
    seen = {generate_personnel_id() for _ in range(50)}
    assert len(seen) == 50


# ---------- utcnow_iso ----------


def test_utcnow_iso_is_utc_iso8601_no_microseconds() -> None:
    stamp = utcnow_iso()
    # 2026-05-15T12:00:00+00:00 — date 'T' time '+00:00'
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", stamp), stamp


# ---------- row_to_personnel ----------


def test_row_to_personnel_handles_iso_strings() -> None:
    row: dict[str, Any] = {
        "personnel_id": "prsn_abc",
        "tenant_id": "t",
        "full_name": "A",
        "position": "op",
        "group_id": None,
        "photo_ref": None,
        "phone": "+7",
        "email": "x@y.z",
        "hired_at": "2024-03-15",
        "created_at": "2024-03-15T00:00:00+00:00",
        "updated_at": "2024-03-15T00:00:00+00:00",
    }
    rec = row_to_personnel(row)
    assert isinstance(rec, DomainPersonnel)
    assert rec.personnel_id == "prsn_abc"
    assert rec.tenant_id == "t"
    assert rec.hired_at == "2024-03-15"


def test_row_to_personnel_coerces_date_objects() -> None:
    import datetime as _dt

    row: dict[str, Any] = {
        "personnel_id": "prsn_x",
        "tenant_id": "t",
        "full_name": "A",
        "position": "op",
        "hired_at": _dt.date(2024, 3, 15),
        "created_at": _dt.datetime(2024, 3, 15, 0, 0, 0, tzinfo=_dt.timezone.utc),
        "updated_at": _dt.datetime(2024, 3, 16, 0, 0, 0, tzinfo=_dt.timezone.utc),
    }
    rec = row_to_personnel(row)
    assert rec.hired_at == "2024-03-15"
    assert rec.created_at == "2024-03-15T00:00:00+00:00"
    assert rec.updated_at == "2024-03-16T00:00:00+00:00"


# ---------- Endpoint registration ----------


def test_personnel_routes_registered_with_correct_prefix() -> None:
    from web_cabinet.api_boundary_v1 import router

    by_path = {}
    for r in router.routes:
        if not hasattr(r, "path"):
            continue
        path = r.path
        if "personnel" not in path:
            continue
        by_path.setdefault(path, set()).update(getattr(r, "methods", ()) or ())
    # Single path /api/app/v1/personnel with GET and POST registered
    assert "/api/app/v1/personnel" in by_path
    methods = by_path["/api/app/v1/personnel"]
    assert "GET" in methods
    assert "POST" in methods


def _extract_required_perms(dep_callable) -> tuple[str, ...]:
    """Walk closure cells of require_permissions(...) -> dep to recover required perms."""
    cells = getattr(dep_callable, "__closure__", None) or ()
    for cell in cells:
        val = cell.cell_contents
        if isinstance(val, tuple) and all(isinstance(v, str) for v in val):
            return val
    return ()


def test_personnel_routes_require_personnel_permissions() -> None:
    """Verify that endpoints declare the personnel.* RBAC gate."""
    from web_cabinet.api_boundary_v1 import router

    found_get = False
    found_post = False
    for r in router.routes:
        path = getattr(r, "path", "")
        if path != "/api/app/v1/personnel":
            continue
        for sub in r.dependant.dependencies:
            call = sub.call
            if call is None or call.__name__ != "dep":
                continue
            perms = _extract_required_perms(call)
            methods = getattr(r, "methods", set()) or set()
            if "GET" in methods:
                assert "personnel.read" in perms, f"GET must declare personnel.read; got {perms}"
                found_get = True
            if "POST" in methods:
                assert "personnel.manage" in perms, f"POST must declare personnel.manage; got {perms}"
                found_post = True
    assert found_get, "GET route not found"
    assert found_post, "POST route not found"
