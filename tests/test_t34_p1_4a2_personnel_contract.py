"""P1-4a-2: Personnel pydantic contract.

Verifies that the Personnel record + list/item responses + request models
honor the project conventions: `schema_version` field with
`serialization_alias='schema'`, optional PII fields, and a `pii_visible`
flag on responses (set by the endpoint after RBAC gate).
"""
from __future__ import annotations

import json

from packages.contracts.api_boundary_v1 import (
    Personnel,
    PersonnelCreateRequest,
    PersonnelListResponse,
    PersonnelResponse,
    PersonnelUpdateRequest,
)


def _dump(model) -> dict:
    return json.loads(model.model_dump_json(by_alias=True))


def test_personnel_minimal_fields() -> None:
    p = Personnel(personnel_id="p-1", full_name="Иванов И.И.", position="Зоотехник")
    payload = _dump(p)
    assert payload["personnel_id"] == "p-1"
    assert payload["full_name"] == "Иванов И.И."
    assert payload["position"] == "Зоотехник"
    # PII optionals default to None
    for pii in ("phone", "email", "hired_at"):
        assert payload[pii] is None


def test_personnel_full_payload_round_trip() -> None:
    p = Personnel(
        personnel_id="p-7",
        full_name="Петрова А.С.",
        position="Ветврач",
        group_id="grp-vet",
        photo_ref="s3://genomeai-personnel/p-7.jpg",
        phone="+7 999 123-45-67",
        email="petrova@example.com",
        hired_at="2024-03-15",
        created_at="2024-03-15T09:00:00Z",
        updated_at="2025-12-01T11:30:00Z",
    )
    payload = _dump(p)
    assert payload["photo_ref"].startswith("s3://")
    assert payload["phone"] and payload["email"] and payload["hired_at"]
    # Round-trip parse
    p2 = Personnel.model_validate(payload)
    assert p2 == p


def test_personnel_list_response_uses_schema_alias() -> None:
    resp = PersonnelListResponse(
        total=2,
        pii_visible=True,
        items=[
            Personnel(personnel_id="p-1", full_name="A", position="zoo"),
            Personnel(personnel_id="p-2", full_name="B", position="vet"),
        ],
    )
    payload = _dump(resp)
    # Wire field is `schema`, not `schema_version`
    assert "schema" in payload
    assert "schema_version" not in payload
    assert payload["schema"] == "genomeai.api.personnel.list.v1"
    assert payload["total"] == 2
    assert payload["pii_visible"] is True
    assert len(payload["items"]) == 2


def test_personnel_item_response_uses_schema_alias() -> None:
    resp = PersonnelResponse(
        pii_visible=False,
        item=Personnel(personnel_id="p-1", full_name="A", position="op"),
    )
    payload = _dump(resp)
    assert payload["schema"] == "genomeai.api.personnel.item.v1"
    assert "schema_version" not in payload
    assert payload["pii_visible"] is False
    assert payload["item"]["personnel_id"] == "p-1"


def test_personnel_list_response_pii_visible_default_false() -> None:
    # Default must be conservative — RBAC has to opt-in
    resp = PersonnelListResponse(total=0)
    assert resp.pii_visible is False


def test_personnel_create_request_requires_name_and_position() -> None:
    # Should work with only required fields
    req = PersonnelCreateRequest(full_name="X Y", position="role")
    assert req.full_name == "X Y"
    assert req.position == "role"
    assert req.group_id is None
    assert req.phone is None


def test_personnel_update_request_all_optional() -> None:
    # Patch semantics — empty body is valid
    req = PersonnelUpdateRequest()
    payload = _dump(req)
    for field in ("full_name", "position", "group_id", "phone", "email", "hired_at", "photo_ref", "user_id"):
        assert payload[field] is None


def test_personnel_user_id_field_present_and_optional() -> None:
    # Personnel record default user_id is None
    p = Personnel(personnel_id="p-1", full_name="A", position="op")
    payload = _dump(p)
    assert "user_id" in payload
    assert payload["user_id"] is None

    # Round-trip with concrete int
    p2 = Personnel(personnel_id="p-2", full_name="B", position="op", user_id=42)
    assert _dump(p2)["user_id"] == 42

    # CreateRequest accepts user_id
    req = PersonnelCreateRequest(full_name="X", position="Y", user_id=7)
    assert req.user_id == 7
