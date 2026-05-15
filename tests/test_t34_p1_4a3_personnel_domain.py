"""P1-4a-3: Personnel domain entity + repository contract.

Pins the repository contract via an in-memory test double. The Postgres
implementation in P1-4a-5 must match these signatures and semantics.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

import pytest

from core.domain.records import Personnel


# ---------- Domain entity invariants ----------


def test_personnel_is_frozen() -> None:
    p = Personnel(personnel_id="p-1", full_name="A B", position="zoo")
    with pytest.raises(Exception):
        p.full_name = "Z"  # type: ignore[misc]


def test_personnel_pii_fields_constant() -> None:
    assert Personnel.PII_FIELDS == ("phone", "email", "hired_at")


def test_personnel_masked_drops_pii_only() -> None:
    p = Personnel(
        personnel_id="p-1",
        full_name="Petrova",
        position="vet",
        group_id="grp-vet",
        photo_ref="s3://x/p-1.jpg",
        phone="+7",
        email="x@y.z",
        hired_at="2024-01-01",
        user_id=42,
        tenant_id="t-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-02T00:00:00Z",
    )
    m = p.masked()
    # PII zeroed
    assert m.phone is None and m.email is None and m.hired_at is None
    # Non-PII preserved (user_id is NOT PII — it's the auth account link)
    assert m.full_name == p.full_name
    assert m.position == p.position
    assert m.group_id == p.group_id
    assert m.photo_ref == p.photo_ref
    assert m.user_id == p.user_id
    assert m.tenant_id == p.tenant_id
    assert m.created_at == p.created_at
    assert m.updated_at == p.updated_at


# ---------- Repository contract (in-memory test double) ----------


class InMemoryPersonnelRepo:
    """Test double that pins the repository contract for P1-4a-5.

    Methods must match the Postgres implementation built in P1-4a-5.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], Personnel] = {}
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"p-{self._seq:04d}"

    def create(
        self,
        *,
        tenant_id: str,
        full_name: str,
        position: str,
        group_id: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        hired_at: Optional[str] = None,
        now: str,
    ) -> Personnel:
        pid = self._next_id()
        rec = Personnel(
            personnel_id=pid,
            full_name=full_name,
            position=position,
            group_id=group_id,
            phone=phone,
            email=email,
            hired_at=hired_at,
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
        self._rows[(tenant_id, pid)] = rec
        return rec

    def get(self, *, tenant_id: str, personnel_id: str) -> Optional[Personnel]:
        return self._rows.get((tenant_id, personnel_id))

    def list(
        self,
        *,
        tenant_id: str,
        group_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[Personnel]]:
        rows = [r for (t, _), r in self._rows.items() if t == tenant_id]
        if group_id is not None:
            rows = [r for r in rows if r.group_id == group_id]
        rows.sort(key=lambda r: r.full_name)
        total = len(rows)
        page = rows[offset : offset + limit]
        return total, page

    def update(
        self,
        *,
        tenant_id: str,
        personnel_id: str,
        now: str,
        **changes: object,
    ) -> Optional[Personnel]:
        key = (tenant_id, personnel_id)
        existing = self._rows.get(key)
        if existing is None:
            return None
        allowed = {"full_name", "position", "group_id", "phone", "email", "hired_at", "photo_ref"}
        patch = {k: v for k, v in changes.items() if k in allowed and v is not None}
        updated = replace(existing, updated_at=now, **patch)  # type: ignore[arg-type]
        self._rows[key] = updated
        return updated

    def delete(self, *, tenant_id: str, personnel_id: str) -> bool:
        return self._rows.pop((tenant_id, personnel_id), None) is not None


# ---------- Contract tests ----------


def test_repo_create_assigns_id_and_timestamps() -> None:
    repo = InMemoryPersonnelRepo()
    rec = repo.create(
        tenant_id="t-1",
        full_name="Ivanov I.I.",
        position="Зоотехник",
        group_id="grp-zoo",
        now="2026-05-15T12:00:00Z",
    )
    assert rec.personnel_id.startswith("p-")
    assert rec.tenant_id == "t-1"
    assert rec.created_at == rec.updated_at == "2026-05-15T12:00:00Z"


def test_repo_tenant_isolation() -> None:
    repo = InMemoryPersonnelRepo()
    a = repo.create(tenant_id="t-A", full_name="A", position="op", now="t")
    repo.create(tenant_id="t-B", full_name="B", position="op", now="t")
    assert repo.get(tenant_id="t-A", personnel_id=a.personnel_id) is not None
    # Other tenant cannot see it
    assert repo.get(tenant_id="t-B", personnel_id=a.personnel_id) is None


def test_repo_list_filters_by_group_and_sorts_by_name() -> None:
    repo = InMemoryPersonnelRepo()
    repo.create(tenant_id="t", full_name="Z", position="op", group_id="g1", now="t")
    repo.create(tenant_id="t", full_name="A", position="op", group_id="g1", now="t")
    repo.create(tenant_id="t", full_name="M", position="op", group_id="g2", now="t")
    total_all, all_rows = repo.list(tenant_id="t")
    assert total_all == 3
    assert [r.full_name for r in all_rows] == ["A", "M", "Z"]
    total_g1, g1_rows = repo.list(tenant_id="t", group_id="g1")
    assert total_g1 == 2
    assert {r.full_name for r in g1_rows} == {"A", "Z"}


def test_repo_list_pagination() -> None:
    repo = InMemoryPersonnelRepo()
    for name in ["A", "B", "C", "D", "E"]:
        repo.create(tenant_id="t", full_name=name, position="op", now="t")
    total, page = repo.list(tenant_id="t", limit=2, offset=2)
    assert total == 5
    assert [r.full_name for r in page] == ["C", "D"]


def test_repo_update_changes_only_provided_fields_and_bumps_updated_at() -> None:
    repo = InMemoryPersonnelRepo()
    rec = repo.create(
        tenant_id="t",
        full_name="Old",
        position="op",
        phone="+1",
        now="2026-05-15T12:00:00Z",
    )
    updated = repo.update(
        tenant_id="t",
        personnel_id=rec.personnel_id,
        now="2026-05-15T13:00:00Z",
        position="manager",
    )
    assert updated is not None
    assert updated.position == "manager"
    assert updated.full_name == "Old"  # untouched
    assert updated.phone == "+1"        # untouched
    assert updated.updated_at == "2026-05-15T13:00:00Z"
    assert updated.created_at == rec.created_at  # immutable


def test_repo_update_missing_returns_none() -> None:
    repo = InMemoryPersonnelRepo()
    assert repo.update(tenant_id="t", personnel_id="nope", now="t") is None


def test_repo_delete_removes_only_target() -> None:
    repo = InMemoryPersonnelRepo()
    a = repo.create(tenant_id="t", full_name="A", position="op", now="t")
    b = repo.create(tenant_id="t", full_name="B", position="op", now="t")
    assert repo.delete(tenant_id="t", personnel_id=a.personnel_id) is True
    assert repo.get(tenant_id="t", personnel_id=a.personnel_id) is None
    assert repo.get(tenant_id="t", personnel_id=b.personnel_id) is not None
    # Idempotent re-delete returns False
    assert repo.delete(tenant_id="t", personnel_id=a.personnel_id) is False
