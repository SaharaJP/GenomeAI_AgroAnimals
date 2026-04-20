from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.config import ConfigValidationError, MappingSchema, field_spec, load_yaml_mapping

from .policy import ALL_PERMISSIONS


class SecurityMatrixConfigError(ValueError):
    pass


def load_permission_matrix(project_root: Path) -> dict[str, Any]:
    path = Path(project_root) / 'configs' / 'security' / 'permission_matrix_v1.yaml'
    try:
        raw = load_yaml_mapping(
            path,
            schema=MappingSchema(
                config_name='permission_matrix_v1',
                fields=(
                    field_spec('version', int, default=1, validator=lambda value: None if int(value) >= 1 else 'version должна быть >= 1'),
                    field_spec('actions', dict, required=True, allow_empty=False),
                ),
            ),
        )
    except ConfigValidationError as exc:
        raise SecurityMatrixConfigError(str(exc)) from exc

    actions = raw.get('actions')
    if not isinstance(actions, dict) or not actions:
        raise SecurityMatrixConfigError(f'Матрица прав {path} должна содержать непустой раздел actions')

    normalized: dict[str, Any] = {'version': int(raw.get('version') or 1), 'actions': {}}
    known_permissions = set(ALL_PERMISSIONS)
    for action_key, meta in actions.items():
        if not isinstance(meta, dict):
            raise SecurityMatrixConfigError(f'actions.{action_key} должен быть объектом')
        perms = meta.get('permissions')
        if not isinstance(perms, list) or not perms or not all(isinstance(p, str) and p.strip() for p in perms):
            raise SecurityMatrixConfigError(
                f'actions.{action_key}.permissions должен быть непустым списком permission-строк'
            )
        permissions = [str(p).strip() for p in perms]
        unknown = [p for p in permissions if p not in known_permissions]
        if unknown:
            raise SecurityMatrixConfigError(
                f'actions.{action_key}.permissions содержит неизвестные permission: {", ".join(sorted(unknown))}'
            )
        normalized['actions'][str(action_key)] = {
            'title': str(meta.get('title') or action_key),
            'permissions': permissions,
        }
    return normalized


def build_permission_matrix_view(*, matrix_cfg: Mapping[str, Any], role_permissions: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    actions = []
    for action_key, meta in (matrix_cfg.get('actions') or {}).items():
        required = [str(p) for p in (meta.get('permissions') or [])]
        row = {
            'key': str(action_key),
            'title': str(meta.get('title') or action_key),
            'permissions': required,
            'roles': {},
        }
        required_set = set(required)
        for role, perms in sorted(role_permissions.items()):
            row['roles'][role] = required_set.issubset(set(str(p) for p in perms or []))
        actions.append(row)
    return {'version': matrix_cfg.get('version') or 1, 'actions': actions}


__all__ = ['SecurityMatrixConfigError', 'build_permission_matrix_view', 'load_permission_matrix']
