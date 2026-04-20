from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from .api_boundary_v1 import (
    AlertsListResponse,
    AssistantResolveTargetRequest,
    AssistantResolveTargetResponse,
    DecisionIntelligenceResponse,
    DecisionsListResponse,
    EconomicsListResponse,
    FeedbackListResponse,
    PilotResponse,
    PlannerResponse,
    ProfileResponse,
    ReadinessResponse,
    ReportsListResponse,
    SupportResponse,
    WorklistsListResponse,
)
from .auth_boundary_v1 import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthLogoutRequest,
    AuthLogoutResponse,
    AuthMeResponse,
    AuthRefreshRequest,
    AuthRefreshResponse,
    AuthSessionRevokeResponse,
    AuthSessionsListResponse,
)

CANONICAL_API_MAJOR_VERSION = 1
CANONICAL_API_VERSION = '1.0.0'
CANONICAL_API_PREFIX = f'/api/app/v{CANONICAL_API_MAJOR_VERSION}'
CANONICAL_OPENAPI_PATH = Path('specs/openapi/genomeai_app_api_v1.openapi.json')
CANONICAL_JSONSCHEMA_PATH = Path('specs/jsonschema/genomeai_app_api_v1.schemas.json')
CANONICAL_VERSIONING_POLICY_PATH = Path('specs/openapi/genomeai_app_api_versioning_policy.json')

CANONICAL_REQUIRED_PATHS = [
    '/api/app/v1/auth/login',
    '/api/app/v1/auth/refresh',
    '/api/app/v1/auth/me',
    '/api/app/v1/auth/logout',
    '/api/app/v1/auth/sessions',
    '/api/app/v1/auth/sessions/{session_id}/revoke',
    '/api/app/v1/alerts',
    '/api/app/v1/worklists',
    '/api/app/v1/planner',
    '/api/app/v1/profiles/{object_type}/{object_id}',
    '/api/app/v1/reports',
    '/api/app/v1/assistant/resolve-target',
    '/api/app/v1/decisions',
    '/api/app/v1/decision-intelligence',
    '/api/app/v1/feedback',
    '/api/app/v1/economics',
    '/api/app/v1/support',
    '/api/app/v1/pilot',
    '/api/app/v1/readiness',
]

CANONICAL_MODELS: dict[str, type[BaseModel]] = {
    cls.__name__: cls
    for cls in [
        AuthLoginRequest,
        AuthLoginResponse,
        AuthRefreshRequest,
        AuthRefreshResponse,
        AuthMeResponse,
        AuthLogoutRequest,
        AuthLogoutResponse,
        AuthSessionsListResponse,
        AuthSessionRevokeResponse,
        AlertsListResponse,
        WorklistsListResponse,
        PlannerResponse,
        ProfileResponse,
        ReportsListResponse,
        AssistantResolveTargetRequest,
        AssistantResolveTargetResponse,
        DecisionsListResponse,
        DecisionIntelligenceResponse,
        FeedbackListResponse,
        EconomicsListResponse,
        SupportResponse,
        PilotResponse,
        ReadinessResponse,
    ]
}


def _sorted(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sorted(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_sorted(x) for x in obj]
    return obj


def build_versioning_policy_manifest() -> dict[str, Any]:
    return {
        'contract_set': 'genomeai.app_boundary',
        'current_major_version': CANONICAL_API_MAJOR_VERSION,
        'current_semver': CANONICAL_API_VERSION,
        'path_prefix': CANONICAL_API_PREFIX,
        'backward_compatibility_rules': [
            'Additive fields MAY be introduced within /api/app/v1 when they are optional or have safe defaults.',
            'Field removal, field rename, enum narrowing, requiredness increase, semantic payload change or path removal is BREAKING.',
            'BREAKING changes require a new path namespace such as /api/app/v2 and parallel contract snapshots.',
            'Web and Android MUST consume the same backend payload semantics; client-specific payload forks are forbidden.',
            'Artifact/run/version-lineage fields remain backward-compatible and must not be repurposed silently.',
        ],
        'breaking_change_detection': {
            'openapi_snapshot': str(CANONICAL_OPENAPI_PATH),
            'jsonschema_snapshot': str(CANONICAL_JSONSCHEMA_PATH),
            'tests': [
                'tests/test_t32_03a_canonical_api_contracts.py',
                'tests/web/test_t32_03a_openapi_boundary.py',
            ],
        },
        'required_paths': list(CANONICAL_REQUIRED_PATHS),
    }


def _collect_refs(node: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get('$ref')
        if isinstance(ref, str) and ref.startswith('#/components/schemas/'):
            refs.add(ref.rsplit('/', 1)[-1])
        for value in node.values():
            refs.update(_collect_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.update(_collect_refs(value))
    return refs


def _collect_referenced_schemas(paths: dict[str, Any], full_schemas: dict[str, Any]) -> dict[str, Any]:
    pending = set(_collect_refs(paths))
    collected: dict[str, Any] = {}
    while pending:
        name = pending.pop()
        if name in collected:
            continue
        schema = full_schemas.get(name)
        if schema is None:
            continue
        collected[name] = schema
        pending.update(_collect_refs(schema) - collected.keys())
    return {name: collected[name] for name in sorted(collected)}


def build_canonical_openapi_spec(*, app) -> dict[str, Any]:
    full = app.openapi()
    full_paths = dict(full.get('paths') or {})
    filtered_paths = {path: full_paths[path] for path in sorted(full_paths) if path in CANONICAL_REQUIRED_PATHS}
    full_schemas = dict(((full.get('components') or {}).get('schemas') or {}))
    filtered_schemas = _collect_referenced_schemas(filtered_paths, full_schemas)
    spec = {
        'openapi': full.get('openapi') or '3.1.0',
        'info': {
            'title': 'GenomeAI Canonical App API',
            'version': CANONICAL_API_VERSION,
            'description': 'Canonical backend API contract set shared by web and Android.',
        },
        'x-genomeai-contract-set': 'app_boundary_v1',
        'x-genomeai-path-prefix': CANONICAL_API_PREFIX,
        'x-genomeai-versioning-policy': build_versioning_policy_manifest(),
        'paths': filtered_paths,
        'components': {'schemas': filtered_schemas},
    }
    return _sorted(spec)


def build_canonical_json_schemas() -> dict[str, Any]:
    schemas = {
        name: _sorted(model.model_json_schema())
        for name, model in sorted(CANONICAL_MODELS.items())
    }
    return _sorted({
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        'contract_set': 'genomeai.app_boundary',
        'version': CANONICAL_API_VERSION,
        'path_prefix': CANONICAL_API_PREFIX,
        'models': schemas,
    })


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sorted(payload), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))
