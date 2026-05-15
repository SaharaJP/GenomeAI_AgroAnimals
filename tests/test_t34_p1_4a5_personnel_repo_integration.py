"""P1-4a-5: PersonnelRepo integration test against live Postgres.

Uses the runtime Postgres connection (GENOMEAI_RUNTIME_POSTGRES_DSN).
All rows live under a tenant_id sandbox unique per run and are cleaned
up in a finalizer. Skipped automatically if the DSN is absent or the
personnel_v1 table is not present (migration P1-4a-4 not yet applied).
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from typing import Iterator

import pytest

psycopg = pytest.importorskip("psycopg")

from core.infra.postgres_compat import CompatConnection  # noqa: E402
from core.infra.repositories import PersonnelRepo  # noqa: E402


def _dsn() -> str | None:
    raw = os.environ.get("GENOMEAI_RUNTIME_POSTGRES_DSN") or os.environ.get("GENOMEAI_DB_DSN")
    return raw.strip() if raw and raw.strip() else None


@contextmanager
def _connect() -> Iterator[CompatConnection]:
    dsn = _dsn()
    if not dsn:
        pytest.skip("no live postgres DSN in env")
    from psycopg.rows import dict_row

    raw = psycopg.connect(dsn, row_factory=dict_row)
    conn = CompatConnection(raw)
    try:
        yield conn
    finally:
        conn.close()


def _table_exists(conn: CompatConnection) -> bool:
    row = conn.execute("SELECT to_regclass('personnel_v1') AS r").fetchone()
    return bool(row and row.get("r"))


@pytest.fixture()
def repo() -> Iterator[PersonnelRepo]:
    with _connect() as conn:
        if not _table_exists(conn):
            pytest.skip("personnel_v1 table absent — apply migration P1-4a-4 first")
        tenant_id = f"test-p1-4a-5-{uuid.uuid4().hex[:8]}"
        r = PersonnelRepo(conn)
        try:
            yield _Sandbox(r, tenant_id)
        finally:
            conn.execute("DELETE FROM personnel_v1 WHERE tenant_id=?", (tenant_id,))
            conn.commit()


class _Sandbox:
    """Wraps PersonnelRepo with a fixed sandbox tenant_id."""

    def __init__(self, repo: PersonnelRepo, tenant_id: str) -> None:
        self.repo = repo
        self.tenant_id = tenant_id

    def insert(self, **kw):
        kw.setdefault("phone", None)
        kw.setdefault("email", None)
        kw.setdefault("hired_at", None)
        kw.setdefault("group_id", None)
        return self.repo.insert(tenant_id=self.tenant_id, **kw)

    def get(self, personnel_id: str):
        return self.repo.get_row(tenant_id=self.tenant_id, personnel_id=personnel_id)

    def list(self, **kw):
        return self.repo.list_rows(tenant_id=self.tenant_id, **kw)

    def update(self, personnel_id: str, sets: list[str], args: list):
        return self.repo.update_fields(
            tenant_id=self.tenant_id,
            personnel_id=personnel_id,
            sets=sets,
            args=args,
        )

    def delete(self, personnel_id: str):
        return self.repo.delete(tenant_id=self.tenant_id, personnel_id=personnel_id)


# ---------- Integration scenarios (mirror P1-4a-3 contract) ----------


def test_insert_and_get_roundtrip(repo: _Sandbox) -> None:
    pid = "prsn-int-1"
    repo.insert(
        personnel_id=pid,
        full_name="Иванов И.И.",
        position="Зоотехник",
        group_id="grp-zoo",
        phone="+7 999 111-22-33",
        email="iv@example.com",
        hired_at="2024-03-15",
        now="2026-05-15T12:00:00+00:00",
    )
    row = repo.get(pid)
    assert row is not None
    assert row["personnel_id"] == pid
    assert row["full_name"] == "Иванов И.И."
    assert row["position"] == "Зоотехник"
    assert row["group_id"] == "grp-zoo"
    assert row["phone"] == "+7 999 111-22-33"
    assert row["email"] == "iv@example.com"
    # hired_at comes back as datetime.date — coerce to ISO for comparison
    assert str(row["hired_at"]) == "2024-03-15"
    assert row["created_at"] is not None
    assert row["updated_at"] is not None


def test_tenant_isolation(repo: _Sandbox) -> None:
    # Insert under the sandbox tenant
    repo.insert(personnel_id="prsn-iso", full_name="A", position="op", now="2026-05-15T12:00:00+00:00")
    # Query a fresh repo with a different tenant — must not see the row
    other_tenant = f"test-other-{uuid.uuid4().hex[:8]}"
    seen = repo.repo.get_row(tenant_id=other_tenant, personnel_id="prsn-iso")
    assert seen is None


def test_list_rows_sorts_and_paginates(repo: _Sandbox) -> None:
    for idx, name in enumerate(["Z", "A", "M", "B", "Y"]):
        repo.insert(personnel_id=f"prsn-page-{idx}", full_name=name, position="op", now="2026-05-15T12:00:00+00:00")
    page_all = repo.list()
    assert page_all["total"] == 5
    assert [r["full_name"] for r in page_all["items"]] == ["A", "B", "M", "Y", "Z"]

    page = repo.list(limit=2, offset=2)
    assert page["total"] == 5
    assert [r["full_name"] for r in page["items"]] == ["M", "Y"]


def test_list_rows_filters_by_group(repo: _Sandbox) -> None:
    repo.insert(personnel_id="prsn-g1-a", full_name="A", position="op", group_id="g1", now="2026-05-15T12:00:00+00:00")
    repo.insert(personnel_id="prsn-g1-b", full_name="B", position="op", group_id="g1", now="2026-05-15T12:00:00+00:00")
    repo.insert(personnel_id="prsn-g2-c", full_name="C", position="op", group_id="g2", now="2026-05-15T12:00:00+00:00")
    page = repo.list(group_id="g1")
    assert page["total"] == 2
    assert {r["full_name"] for r in page["items"]} == {"A", "B"}


def test_update_fields_changes_only_supplied_columns(repo: _Sandbox) -> None:
    pid = "prsn-upd-1"
    repo.insert(
        personnel_id=pid,
        full_name="Old",
        position="op",
        phone="+1",
        now="2026-05-15T12:00:00+00:00",
    )
    affected = repo.update(
        pid,
        sets=["position=?", "updated_at=?"],
        args=["manager", "2026-05-15T13:00:00+00:00"],
    )
    assert affected == 1
    row = repo.get(pid)
    assert row["position"] == "manager"
    assert row["full_name"] == "Old"  # untouched
    assert row["phone"] == "+1"        # untouched


def test_update_fields_missing_row_returns_zero(repo: _Sandbox) -> None:
    affected = repo.update(
        "prsn-missing",
        sets=["position=?", "updated_at=?"],
        args=["x", "2026-05-15T12:00:00+00:00"],
    )
    assert affected == 0


def test_delete_removes_only_target_and_is_idempotent(repo: _Sandbox) -> None:
    repo.insert(personnel_id="prsn-del-a", full_name="A", position="op", now="2026-05-15T12:00:00+00:00")
    repo.insert(personnel_id="prsn-del-b", full_name="B", position="op", now="2026-05-15T12:00:00+00:00")
    assert repo.delete("prsn-del-a") == 1
    assert repo.get("prsn-del-a") is None
    assert repo.get("prsn-del-b") is not None
    assert repo.delete("prsn-del-a") == 0  # already gone


def test_indexes_present(repo: _Sandbox) -> None:
    # Sanity: the two performance indexes from the migration must exist
    rows = repo.repo.conn.execute(
        "SELECT indexname FROM pg_indexes WHERE tablename='personnel_v1'",
        (),
    ).fetchall()
    names = {r["indexname"] for r in rows}
    assert "idx_personnel_v1_tenant_name" in names
    assert "idx_personnel_v1_tenant_group" in names
