"""P1-4a-1: Personnel RBAC permissions matrix.

Verifies that personnel.read / personnel.read_pii / personnel.manage
are registered in ALL_PERMISSIONS and bound to roles per coordinator decision:

  ADMIN     → read + read_pii + manage (via ALL_PERMISSIONS)
  DIRECTOR  → read + read_pii + manage (HR-уровень)
  ZOOTECH   → read + read_pii          (operational manager)
  VET       → read + read_pii          (assigns vet tasks)
  OPERATOR  → read                     (видит коллег, без PII)
  VIEWER    → read                     (структура без PII)
  CONSULTANT→ read                     (external, без PII)
  PARTNER   → read                     (external, без PII)
"""
from __future__ import annotations

from core import security as rbac


def test_personnel_permissions_registered_in_all_permissions() -> None:
    assert rbac.PERM_PERSONNEL_READ == "personnel.read"
    assert rbac.PERM_PERSONNEL_READ_PII == "personnel.read_pii"
    assert rbac.PERM_PERSONNEL_MANAGE == "personnel.manage"
    assert rbac.PERM_PERSONNEL_READ in rbac.ALL_PERMISSIONS
    assert rbac.PERM_PERSONNEL_READ_PII in rbac.ALL_PERMISSIONS
    assert rbac.PERM_PERSONNEL_MANAGE in rbac.ALL_PERMISSIONS


def _perms(role: str) -> set[str]:
    return set(rbac.DEFAULT_ROLE_PERMISSIONS[role])


def test_admin_has_all_personnel_permissions() -> None:
    admin = _perms(rbac.ROLE_ADMIN)
    assert rbac.PERM_PERSONNEL_READ in admin
    assert rbac.PERM_PERSONNEL_READ_PII in admin
    assert rbac.PERM_PERSONNEL_MANAGE in admin


def test_director_has_full_personnel_access() -> None:
    director = _perms(rbac.ROLE_DIRECTOR)
    assert rbac.PERM_PERSONNEL_READ in director
    assert rbac.PERM_PERSONNEL_READ_PII in director
    assert rbac.PERM_PERSONNEL_MANAGE in director


def test_zootech_and_vet_have_read_and_pii_but_not_manage() -> None:
    for role in (rbac.ROLE_ZOOTECH, rbac.ROLE_VET):
        perms = _perms(role)
        assert rbac.PERM_PERSONNEL_READ in perms, role
        assert rbac.PERM_PERSONNEL_READ_PII in perms, role
        assert rbac.PERM_PERSONNEL_MANAGE not in perms, role


def test_operator_viewer_consultant_partner_have_read_only() -> None:
    for role in (
        rbac.ROLE_OPERATOR,
        rbac.ROLE_VIEWER,
        rbac.ROLE_CONSULTANT,
        rbac.ROLE_PARTNER,
    ):
        perms = _perms(role)
        assert rbac.PERM_PERSONNEL_READ in perms, role
        assert rbac.PERM_PERSONNEL_READ_PII not in perms, role
        assert rbac.PERM_PERSONNEL_MANAGE not in perms, role


def test_ensure_permissions_blocks_pii_for_operator() -> None:
    operator_perms = rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_OPERATOR]
    try:
        rbac.ensure_permissions(
            operator_perms,
            rbac.PERM_PERSONNEL_READ_PII,
            role=rbac.ROLE_OPERATOR,
            operation="personnel.pii.view",
        )
    except rbac.PermissionDenied as exc:
        assert rbac.PERM_PERSONNEL_READ_PII in exc.missing_permissions
    else:
        raise AssertionError("Operator must not have personnel.read_pii")


def test_ensure_permissions_blocks_manage_for_zootech() -> None:
    zootech_perms = rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_ZOOTECH]
    try:
        rbac.ensure_permissions(
            zootech_perms,
            rbac.PERM_PERSONNEL_MANAGE,
            role=rbac.ROLE_ZOOTECH,
            operation="personnel.manage",
        )
    except rbac.PermissionDenied as exc:
        assert rbac.PERM_PERSONNEL_MANAGE in exc.missing_permissions
    else:
        raise AssertionError("Zootech must not have personnel.manage")
