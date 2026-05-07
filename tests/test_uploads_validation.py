"""validate_rows: required, type, range, FK, duplicate."""
from __future__ import annotations

import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _ensure_animal(tenant_id, animal_id, farm_id='F1'):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dm_farms (tenant_id, farm_id, farm_name) VALUES (%s, %s, 'F1') "
                "ON CONFLICT DO NOTHING",
                (tenant_id, farm_id),
            )
            cur.execute(
                "INSERT INTO dm_animals (tenant_id, animal_id, farm_id) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (tenant_id, animal_id, farm_id),
            )
        conn.commit()


def _cleanup(tenant_id):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dm_milkings_daily WHERE tenant_id=%s", (tenant_id,))
            cur.execute("DELETE FROM dm_animals WHERE tenant_id=%s", (tenant_id,))
            cur.execute("DELETE FROM dm_farms WHERE tenant_id=%s", (tenant_id,))
        conn.commit()


def test_required_field_missing():
    from web_cabinet.uploads_v1 import validate_rows
    rows = [{'animal_id': '', 'date': '2026-05-01', 'milk_kg': 28.5}]
    result = validate_rows('milkings', rows, tenant_id='vt_tx')
    assert len(result.errors) == 1
    assert result.errors[0].field == 'animal_id'


def test_type_coercion_failure():
    from web_cabinet.uploads_v1 import validate_rows
    rows = [{'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 'abc'}]
    result = validate_rows('milkings', rows, tenant_id='vt_tx')
    assert any(e.field == 'milk_kg' for e in result.errors)


def test_range_violation():
    from web_cabinet.uploads_v1 import validate_rows
    rows = [{'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 250.0}]
    result = validate_rows('milkings', rows, tenant_id='vt_tx')
    assert any(e.field == 'milk_kg' for e in result.errors)


def test_fk_missing_animal():
    from web_cabinet.uploads_v1 import validate_rows
    tenant = f'vt_fk_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    rows = [{'animal_id': 'NOT_EXIST', 'date': '2026-05-01', 'milk_kg': 28.5}]
    result = validate_rows('milkings', rows, tenant_id=tenant)
    assert any(e.field == 'animal_id' for e in result.errors)


def test_fk_present_passes():
    from web_cabinet.uploads_v1 import validate_rows
    tenant = f'vt_fkok_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        rows = [{'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5}]
        result = validate_rows('milkings', rows, tenant_id=tenant)
        assert len(result.errors) == 0
        assert len(result.valid_rows) == 1
    finally:
        _cleanup(tenant)


def test_duplicate_detected():
    from web_cabinet.uploads_v1 import validate_rows
    from web_cabinet.insights_v1 import _conn
    tenant = f'vt_dup_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dm_milkings_daily (tenant_id, record_id, animal_id, date, milk_kg, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())",
                    (tenant, 'r1', 'A1', '2026-05-01', 28.5),
                )
            conn.commit()
        rows = [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
            {'animal_id': 'A1', 'date': '2026-05-02', 'milk_kg': 29.0},
        ]
        result = validate_rows('milkings', rows, tenant_id=tenant)
        assert result.duplicates == 1
        assert len(result.valid_rows) == 1
    finally:
        _cleanup(tenant)
