"""Token cache + commit_rows."""
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


def test_token_create_and_commit():
    from web_cabinet.uploads_v1 import store_preview_token, commit_rows
    tenant = f'vt_c_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        token = store_preview_token('milkings', tenant, [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
        ])
        assert isinstance(token, str) and len(token) > 8
        resp = commit_rows(token, tenant_id=tenant)
        assert resp.inserted == 1
    finally:
        _cleanup(tenant)


def test_commit_unknown_token_returns_410():
    from web_cabinet.uploads_v1 import commit_rows, TokenExpired
    with pytest.raises(TokenExpired):
        commit_rows('bogus_token', tenant_id='any')


def test_commit_consumed_once():
    from web_cabinet.uploads_v1 import store_preview_token, commit_rows, TokenExpired
    tenant = f'vt_cs_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant)
    _ensure_animal(tenant, 'A1')
    try:
        token = store_preview_token('milkings', tenant, [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
        ])
        commit_rows(token, tenant_id=tenant)
        with pytest.raises(TokenExpired):
            commit_rows(token, tenant_id=tenant)
    finally:
        _cleanup(tenant)


def test_commit_tenant_mismatch():
    from web_cabinet.uploads_v1 import store_preview_token, commit_rows, TenantMismatch
    tenant_a = f'vt_a_{uuid.uuid4().hex[:6]}'
    tenant_b = f'vt_b_{uuid.uuid4().hex[:6]}'
    _cleanup(tenant_a); _cleanup(tenant_b)
    _ensure_animal(tenant_a, 'A1')
    try:
        token = store_preview_token('milkings', tenant_a, [
            {'animal_id': 'A1', 'date': '2026-05-01', 'milk_kg': 28.5},
        ])
        with pytest.raises(TenantMismatch):
            commit_rows(token, tenant_id=tenant_b)
    finally:
        _cleanup(tenant_a); _cleanup(tenant_b)
