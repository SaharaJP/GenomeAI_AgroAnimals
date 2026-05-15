"""P1-5: DB-overrides on top of YAML permission matrix.

Effective permissions for a role:
    yaml_baseline.union(grants_in_db).difference(revokes_in_db)

The YAML matrix (configs/security/permission_matrix_v1.yaml + DEFAULT_ROLE_PERMISSIONS)
is the immutable source of truth at boot time. The
`role_permissions_overrides_v1` table can layer per-pair (role, permission)
adjustments at runtime with a single effect: 'grant' or 'revoke'.

This module is pure infra over a DB connection — it does NOT enforce
RBAC; callers (api_boundary, deps) must gate by admin.manage permission
before invoking write helpers.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional


Effect = str  # 'grant' | 'revoke'

GRANT: Effect = "grant"
REVOKE: Effect = "revoke"


def list_overrides(conn: Any) -> list[dict[str, Any]]:
    """Return all override rows ordered by role, permission."""
    try:
        rows = conn.execute(
            "SELECT role, permission, effect, created_at, created_by_user_id, created_by_username "
            "FROM role_permissions_overrides_v1 ORDER BY role, permission"
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


def list_overrides_for_role(conn: Any, *, role: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT role, permission, effect, created_at, created_by_user_id, created_by_username "
            "FROM role_permissions_overrides_v1 WHERE role=? ORDER BY permission",
            (role,),
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


def get_override(conn: Any, *, role: str, permission: str) -> Optional[dict[str, Any]]:
    try:
        row = conn.execute(
            "SELECT role, permission, effect, created_at, created_by_user_id, created_by_username "
            "FROM role_permissions_overrides_v1 WHERE role=? AND permission=?",
            (role, permission),
        ).fetchone()
    except Exception:
        return None
    return dict(row) if row else None


def apply_effective_permissions(
    *,
    baseline: Iterable[str],
    overrides: Iterable[dict[str, Any]],
) -> list[str]:
    """Return the effective permission list after applying overrides to baseline.

    `baseline` — list/set of permissions from the YAML matrix for one role.
    `overrides` — rows {role, permission, effect} that target THE SAME role.
    Permissions are returned sorted, deduplicated.
    """
    eff = set(baseline)
    for row in overrides:
        perm = row.get("permission")
        eff_kind = row.get("effect")
        if not perm:
            continue
        if eff_kind == GRANT:
            eff.add(perm)
        elif eff_kind == REVOKE:
            eff.discard(perm)
    return sorted(eff)


def set_override(
    conn: Any,
    *,
    role: str,
    permission: str,
    effect: Effect,
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert an override and return the new row.

    Caller MUST validate `permission` against ALL_PERMISSIONS and `role` against
    the known role catalog. Caller MUST emit audit `iam.permission.{grant|revoke}`
    after this call returns successfully.
    """
    if effect not in (GRANT, REVOKE):
        raise ValueError(f"unsupported effect: {effect!r}")
    conn.execute(
        """
        INSERT INTO role_permissions_overrides_v1
            (role, permission, effect, created_at, created_by_user_id, created_by_username)
        VALUES (?, ?, ?, NOW(), ?, ?)
        ON CONFLICT (role, permission) DO UPDATE
            SET effect = EXCLUDED.effect,
                created_at = NOW(),
                created_by_user_id = EXCLUDED.created_by_user_id,
                created_by_username = EXCLUDED.created_by_username
        """,
        (role, permission, effect, actor_user_id, actor_username),
    )
    conn.commit()
    row = get_override(conn, role=role, permission=permission)
    if row is None:
        raise RuntimeError("set_override lost row after upsert")
    return row


def clear_override(
    conn: Any,
    *,
    role: str,
    permission: str,
) -> Optional[dict[str, Any]]:
    """Remove an override (revert to YAML default). Returns the removed row or None."""
    before = get_override(conn, role=role, permission=permission)
    if before is None:
        return None
    conn.execute(
        "DELETE FROM role_permissions_overrides_v1 WHERE role=? AND permission=?",
        (role, permission),
    )
    conn.commit()
    return before


__all__ = [
    "GRANT",
    "REVOKE",
    "apply_effective_permissions",
    "clear_override",
    "get_override",
    "list_overrides",
    "list_overrides_for_role",
    "set_override",
]
