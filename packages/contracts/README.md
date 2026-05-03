# packages/contracts

Каталог для versioned shared contracts между backend API, web и Android.

## Что должно лежать здесь

- request/response schemas
- shared enums
- OpenAPI snapshots/generated clients
- compatibility notes
- contract changelog

## Правило

Любой новый UI flow обязан опираться на контракт из backend, а не на implicit структуру Python-объектов или Streamlit state.


## Canonical API freeze (T32-03A)

Checked-in explicit specs:

- `specs/openapi/genomeai_app_api_v1.openapi.json`
- `specs/jsonschema/genomeai_app_api_v1.schemas.json`
- `specs/openapi/genomeai_app_api_versioning_policy.json`

Regenerate after intentional contract changes:

```bash
PYTHONPATH="$PWD/src:$PYTHONPATH" python scripts/export_canonical_api_contracts.py
```
