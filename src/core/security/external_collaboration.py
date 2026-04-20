from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from .policy import (
    PERM_COLLAB_APPROVAL_REQUEST,
    PERM_COLLAB_APPROVAL_REVIEW,
    PERM_COLLAB_COMMENTS_WRITE,
    PERM_COLLAB_RECOMMENDATIONS_WRITE,
    ROLE_CONSULTANT,
    ROLE_PARTNER,
    normalize_permissions,
)

COLLAB_MODE_INTERNAL = 'internal'
COLLAB_MODE_EXTERNAL_CONSULTANT = 'external_consultant'
COLLAB_MODE_EXTERNAL_PARTNER = 'external_partner'


@dataclass(frozen=True, slots=True)
class CollaborationBoundary:
    role: str
    collaboration_mode: str
    external_org: str | None
    allowed_farm_ids: tuple[str, ...]
    allowed_site_ids: tuple[str, ...]
    permissions: tuple[str, ...]
    flags: dict[str, Any]

    @property
    def is_external(self) -> bool:
        return self.collaboration_mode in {COLLAB_MODE_EXTERNAL_CONSULTANT, COLLAB_MODE_EXTERNAL_PARTNER}

    @property
    def allow_comments(self) -> bool:
        return bool(self.flags.get('allow_comments', PERM_COLLAB_COMMENTS_WRITE in set(self.permissions)))

    @property
    def allow_recommendations(self) -> bool:
        return bool(self.flags.get('allow_recommendations', PERM_COLLAB_RECOMMENDATIONS_WRITE in set(self.permissions)))

    @property
    def allow_approval_requests(self) -> bool:
        return bool(self.flags.get('allow_approval_requests', PERM_COLLAB_APPROVAL_REQUEST in set(self.permissions)))

    @property
    def allow_approval_review(self) -> bool:
        return bool(self.flags.get('allow_approval_review', PERM_COLLAB_APPROVAL_REVIEW in set(self.permissions)))

    def summary(self) -> dict[str, Any]:
        return {
            'role': self.role,
            'collaboration_mode': self.collaboration_mode,
            'is_external': self.is_external,
            'external_org': self.external_org,
            'allowed_farm_ids': list(self.allowed_farm_ids),
            'allowed_site_ids': list(self.allowed_site_ids),
            'allow_comments': self.allow_comments,
            'allow_recommendations': self.allow_recommendations,
            'allow_approval_requests': self.allow_approval_requests,
            'allow_approval_review': self.allow_approval_review,
        }


_DEFAULTS = {
    ROLE_CONSULTANT: {
        'collaboration_mode': COLLAB_MODE_EXTERNAL_CONSULTANT,
        'flags': {'allow_comments': True, 'allow_recommendations': True, 'allow_approval_requests': True, 'allow_approval_review': False},
    },
    ROLE_PARTNER: {
        'collaboration_mode': COLLAB_MODE_EXTERNAL_PARTNER,
        'flags': {'allow_comments': True, 'allow_recommendations': True, 'allow_approval_requests': True, 'allow_approval_review': False},
    },
}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _clean_list(values: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = _clean(value)
        if text and text not in out:
            out.append(text)
    return out


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return _clean_list(value)
    text = _clean(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = [x.strip() for x in text.split(',') if x.strip()]
    return _clean_list(parsed if isinstance(parsed, (list, tuple, set)) else [parsed])


def _load_json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def load_external_collaboration_policy(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root or Path.cwd())
    path = root / 'configs' / 'security' / 'external_collaboration_v1.yaml'
    if not path.exists():
        return {'version': 1, 'roles': dict(_DEFAULTS), 'internal_review_roles': ['Admin', 'Director']}
    raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(raw, Mapping):
        return {'version': 1, 'roles': dict(_DEFAULTS), 'internal_review_roles': ['Admin', 'Director']}
    roles = dict(_DEFAULTS)
    roles.update(dict(raw.get('roles') or {}))
    return {
        'version': int(raw.get('version') or 1),
        'roles': roles,
        'internal_review_roles': [str(x) for x in (raw.get('internal_review_roles') or ['Admin', 'Director']) if _clean(x)],
    }


def build_collaboration_boundary(user: Mapping[str, Any] | None, *, project_root: str | Path | None = None) -> CollaborationBoundary:
    raw = dict(user or {})
    role = _clean(raw.get('role')) or 'Viewer'
    cfg = load_external_collaboration_policy(project_root=project_root)
    role_cfg = dict((cfg.get('roles') or {}).get(role) or {})
    default_mode = _clean(role_cfg.get('collaboration_mode')) or (COLLAB_MODE_EXTERNAL_CONSULTANT if role == ROLE_CONSULTANT else COLLAB_MODE_EXTERNAL_PARTNER if role == ROLE_PARTNER else COLLAB_MODE_INTERNAL)
    mode = _clean(raw.get('collaboration_mode')) or default_mode
    external_org = _clean(raw.get('external_org')) or None
    flags = dict(role_cfg.get('flags') or {})
    flags.update(_load_json_mapping(raw.get('collaboration_flags_json') or raw.get('collaboration_flags') or {}))
    perms = normalize_permissions(raw.get('permissions') or ())
    return CollaborationBoundary(
        role=role,
        collaboration_mode=mode,
        external_org=external_org,
        allowed_farm_ids=tuple(_load_json_list(raw.get('allowed_farm_ids_json') or raw.get('allowed_farm_ids') or [])),
        allowed_site_ids=tuple(_load_json_list(raw.get('allowed_site_ids_json') or raw.get('allowed_site_ids') or [])),
        permissions=perms,
        flags=flags,
    )


def boundary_allows_scope(boundary: CollaborationBoundary, *, farm_id: str | None, site_id: str | None) -> bool:
    farm_v = _clean(farm_id)
    site_v = _clean(site_id)
    if not boundary.is_external:
        return True
    # deny-by-default if no scope configured for external users
    if not boundary.allowed_farm_ids and not boundary.allowed_site_ids:
        return False
    if boundary.allowed_site_ids:
        return bool(site_v and site_v in set(boundary.allowed_site_ids))
    if boundary.allowed_farm_ids:
        return bool(farm_v and farm_v in set(boundary.allowed_farm_ids))
    return False


def filter_rows_for_boundary(rows: Sequence[Mapping[str, Any]], boundary: CollaborationBoundary) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        if boundary_allows_scope(boundary, farm_id=row.get('farm_id'), site_id=row.get('site_id')):
            out.append(row)
    return out


def allowed_page_roles_for_external(base_roles: Sequence[str] | None = None) -> list[str]:
    out = [str(x) for x in (base_roles or []) if _clean(x)]
    for role in (ROLE_CONSULTANT, ROLE_PARTNER):
        if role not in out:
            out.append(role)
    return out


__all__ = [
    'COLLAB_MODE_INTERNAL',
    'COLLAB_MODE_EXTERNAL_CONSULTANT',
    'COLLAB_MODE_EXTERNAL_PARTNER',
    'CollaborationBoundary',
    'allowed_page_roles_for_external',
    'boundary_allows_scope',
    'build_collaboration_boundary',
    'filter_rows_for_boundary',
    'load_external_collaboration_policy',
]
