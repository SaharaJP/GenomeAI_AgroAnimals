"""Admin overrides for /integrations/health enable/disable state (P1-6b slice 1).

Each row in `integration_overrides_v1` says "this integration is forcibly
enabled/disabled for this tenant". Absence of a row = natural state from
the provider.

The aggregator (`collect_health` in src/core/interoperability/integrations_health.py)
calls `apply_overrides()` after running providers to override status='disabled'
and set an admin note on the rows the operator has switched off.
"""
from __future__ import annotations

from typing import Any, Optional


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    updated_at = d.get('updated_at')
    return {
        'integration_id': str(d.get('integration_id') or ''),
        'tenant_id': str(d.get('tenant_id') or ''),
        'enabled': bool(d.get('enabled')),
        'updated_at': updated_at.isoformat() if hasattr(updated_at, 'isoformat') else (str(updated_at) if updated_at else None),
        'updated_by_user_id': int(d['updated_by_user_id']) if d.get('updated_by_user_id') is not None else None,
        'updated_by_username': d.get('updated_by_username'),
    }


def get_override(conn: Any, *, integration_id: str, tenant_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT integration_id, tenant_id, enabled, updated_at, updated_by_user_id, updated_by_username "
        "FROM integration_overrides_v1 WHERE integration_id=? AND tenant_id=?",
        (integration_id, tenant_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_overrides_for_tenant(conn: Any, *, tenant_id: str) -> dict[str, dict[str, Any]]:
    """Return {integration_id: override_dict} for a tenant, for batch lookup."""
    cur = conn.execute(
        "SELECT integration_id, tenant_id, enabled, updated_at, updated_by_user_id, updated_by_username "
        "FROM integration_overrides_v1 WHERE tenant_id=?",
        (tenant_id,),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        d = _row_to_dict(row)
        out[d['integration_id']] = d
    return out


def upsert_override(
    conn: Any,
    *,
    integration_id: str,
    tenant_id: str,
    enabled: bool,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """Returns (before, after) for audit trail."""
    before = get_override(conn, integration_id=integration_id, tenant_id=tenant_id)
    conn.execute(
        """
        INSERT INTO integration_overrides_v1
            (integration_id, tenant_id, enabled, updated_at, updated_by_user_id, updated_by_username)
        VALUES (?, ?, ?, NOW(), ?, ?)
        ON CONFLICT (integration_id, tenant_id) DO UPDATE SET
            enabled=excluded.enabled,
            updated_at=NOW(),
            updated_by_user_id=excluded.updated_by_user_id,
            updated_by_username=excluded.updated_by_username
        """,
        (integration_id, tenant_id, bool(enabled), user_id, username),
    )
    after = get_override(conn, integration_id=integration_id, tenant_id=tenant_id)
    assert after is not None  # we just inserted
    return before, after


def apply_overrides(rows: list, overrides: dict[str, dict[str, Any]]) -> list:
    """Mutate rows in place: force status='disabled' on rows the admin has switched off.

    `rows` is a list of IntegrationHealth-shaped objects (dataclass or dict).
    `overrides` is the dict returned by list_overrides_for_tenant.

    Rows the admin explicitly *enabled* are left at their natural status (provider's
    answer wins). Rows the admin *disabled* are forced to status='disabled' with a
    note explaining the override.
    """
    if not overrides or not rows:
        return rows
    for row in rows:
        # Support both dataclass-like (.id) and dict-like ('id') access without
        # importing dataclasses at module top.
        rid = getattr(row, 'id', None) or (row.get('id') if isinstance(row, dict) else None)
        if not rid:
            continue
        ov = overrides.get(rid)
        if ov is None:
            continue
        if not ov.get('enabled'):
            existing_note = getattr(row, 'note', None) or (row.get('note') if isinstance(row, dict) else None) or ''
            admin_note = 'Отключено администратором'
            note = f"{admin_note} · {existing_note}" if existing_note else admin_note
            if hasattr(row, '__dict__'):
                row.status = 'disabled'  # type: ignore[attr-defined]
                row.note = note  # type: ignore[attr-defined]
            else:
                row['status'] = 'disabled'
                row['note'] = note
    return rows


__all__ = [
    'apply_overrides',
    'get_override',
    'list_overrides_for_tenant',
    'upsert_override',
]
