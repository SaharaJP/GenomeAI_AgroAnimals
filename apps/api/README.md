# apps/api

Будущий production API слой GenomeAI AgroAnimals.

На текущем шаге каталог создан как архитектурный anchor, чтобы новый server-side код больше не размазывался между legacy `web_cabinet/` и UI-адаптерами.

## Назначение

- HTTP API
- auth/session/token boundary
- DTO/contracts mapping
- background job triggering
- OpenAPI publishing
- readiness/liveness/admin endpoints

## Источники миграции

- `src/core/` — use-cases и доменная логика
- `web_cabinet/` — legacy server adapter/fallback, из которого будет выноситься API surface

## Правило

Новый backend endpoint сначала проектируется как контракт, затем реализуется через core use-cases.


## Текущий boundary namespace

На этапе T32-02 первый shared boundary опубликован в namespace `/api/app/v1/*`.
Новые web/mobile daily-use flows должны добавляться туда, а не в legacy `/api/*_v1|v2` маршруты.


## Canonical contract snapshots

Current canonical web/mobile API freeze lives in:

- `specs/openapi/genomeai_app_api_v1.openapi.json`
- `specs/jsonschema/genomeai_app_api_v1.schemas.json`
- `docs/api_contracts_and_versioning.md`
