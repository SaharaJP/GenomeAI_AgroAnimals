from __future__ import annotations

from pathlib import Path

from packages.contracts.canonical_api_contracts import (
    CANONICAL_JSONSCHEMA_PATH,
    CANONICAL_OPENAPI_PATH,
    CANONICAL_VERSIONING_POLICY_PATH,
    build_canonical_json_schemas,
    build_canonical_openapi_spec,
    build_versioning_policy_manifest,
    write_json,
)
from web_cabinet.app import app


def main() -> int:
    write_json(CANONICAL_OPENAPI_PATH, build_canonical_openapi_spec(app=app))
    write_json(CANONICAL_JSONSCHEMA_PATH, build_canonical_json_schemas())
    write_json(CANONICAL_VERSIONING_POLICY_PATH, build_versioning_policy_manifest())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
