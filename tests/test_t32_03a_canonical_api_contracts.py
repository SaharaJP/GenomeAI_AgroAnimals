from __future__ import annotations

from packages.contracts.canonical_api_contracts import (
    CANONICAL_JSONSCHEMA_PATH,
    CANONICAL_OPENAPI_PATH,
    CANONICAL_REQUIRED_PATHS,
    CANONICAL_VERSIONING_POLICY_PATH,
    build_canonical_json_schemas,
    build_versioning_policy_manifest,
    load_json,
)


def test_t32_03a_jsonschema_snapshot_matches_generated() -> None:
    assert build_canonical_json_schemas() == load_json(CANONICAL_JSONSCHEMA_PATH)


def test_t32_03a_versioning_policy_snapshot_matches_generated() -> None:
    assert build_versioning_policy_manifest() == load_json(CANONICAL_VERSIONING_POLICY_PATH)


def test_t32_03a_snapshot_lists_required_paths() -> None:
    spec = load_json(CANONICAL_OPENAPI_PATH)
    assert sorted(spec['paths']) == sorted(CANONICAL_REQUIRED_PATHS)
