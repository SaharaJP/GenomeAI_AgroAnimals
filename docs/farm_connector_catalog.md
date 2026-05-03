# T26-04 — Farm connector catalog

## Что добавлено

`T26-04` расширяет connector framework без попытки сделать глубокие вендорские интеграции за один шаг.

Слой состоит из двух частей:

1. **Active connectors status** — для уже подключённых connector configs платформа показывает:
   - `source_system`
   - `export_mode`
   - `source_status`
   - `freshness`
   - `source_export_at`
   - `last_pull_at`
   - `last_pull_status`
   - `sync_lag_minutes`
   - `last_error`
   - `action_hint`
   - `supported_contracts`

2. **Representative connector catalog** — набор reusable adapter blueprints для типовых farm systems / exports:
   - `dairycomp_305_batch`
   - `selex_batch`
   - `onec_livestock_batch`

## Где лежит каталог

- `configs/connector_catalog/*.yaml` — catalog blueprints
- `configs/connector_catalog/examples/*.yaml` — representative connector configs
- `configs/mappings/connectors/...` — reusable mapping templates

## Почему это не deep integration

Каталог не обещает live API integration со всеми вендорами.

Это reusable framework для staged interoperability:
- reusable config shape
- reusable schedules
- reusable mapping template pointers
- diagnostics / action hints
- explicit contract coverage

## Source status semantics

Bounded статусы:

- `disabled`
- `stub`
- `source_error`
- `waiting_source`
- `refresh_available`
- `never_pulled`
- `in_sync`
- `stale_batch`

Они intentionally explainable и подходят для batch/export workflows.

## Action-oriented diagnostics

Ошибки и предупреждения не скрываются. В UI показываются:

- `last_error`
- `action_hint`
- binding-level diagnostics в `binding_rows`

Это нужно, чтобы staged rollout не зависел от ручных ad hoc scripts и "магических" догадок оператора.

## Ограничения

- Нет универсального live connector SDK для всех вендоров.
- `source_status` наследует ограничения batch/export contour.
- `freshness` и `sync_lag` не должны интерпретироваться как near-real-time для batch systems.
- Representative adapters — это starter profiles; их нужно уточнять под конкретный farm export.
