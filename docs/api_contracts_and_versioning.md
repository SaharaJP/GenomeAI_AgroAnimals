# T32-03A — Canonical API contracts / OpenAPI freeze

## Что зафиксировано

На этом шаге контрактный слой для web и Android зафиксирован не только кодом, но и явными snapshot-спецификациями:

- canonical OpenAPI snapshot: `specs/openapi/genomeai_app_api_v1.openapi.json`
- canonical JSON-schema snapshot: `specs/jsonschema/genomeai_app_api_v1.schemas.json`
- versioning policy manifest: `specs/openapi/genomeai_app_api_versioning_policy.json`

Источник правды по DTO/response models остаётся в `packages/contracts/*`, но теперь любой drift обязан проходить через регенерацию snapshot-спецификации и тестовый gate.

## Покрытые поверхности

Канонический `/api/app/v1/*` контрактный слой включает:

- auth/session
- alerts
- worklists
- planner
- animal/group profiles
- reports
- assistant
- decisions
- decision intelligence
- feedback
- economics
- support
- pilot
- readiness

Это тот контрактный слой, который должен использоваться и React/Next.js web, и Android-клиентом.

## Правила версионирования

Текущий major namespace: `/api/app/v1`.

Внутри `/api/app/v1` допустимы только backward-compatible изменения:

- новые optional fields;
- новые endpoint query params с safe defaults;
- новые additive sections, которые не меняют смысл старых payloads.

Считается breaking change и требует нового namespace, например `/api/app/v2`:

- удаление или rename поля;
- изменение payload semantics без смены версии;
- превращение optional поля в required;
- сужение enum/статусов;
- удаление endpoint/path;
- расхождение web/mobile payload semantics.

## Как обновлять snapshot

После осознанного contract change:

```bash
PYTHONPATH="$PWD/src:$PYTHONPATH" python scripts/export_canonical_api_contracts.py
```

После этого нужно прогнать tests/gates и убедиться, что изменение было намеренным.

## Как детектируется drift

Drift/breaking changes детектируются через snapshot tests:

- `tests/test_t32_03a_canonical_api_contracts.py`
- `tests/web/test_t32_03a_openapi_boundary.py`

Если backend payload shape изменился, а snapshot не обновлён, тесты падают.

## Что это даёт команде

- backend, web и mobile ориентируются на один и тот же contract set;
- payload semantics не расходятся по клиентам;
- любые breaking changes видны до массового переноса UI;
- lineage semantics (`data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`) остаются явно закреплёнными в контрактном слое.
