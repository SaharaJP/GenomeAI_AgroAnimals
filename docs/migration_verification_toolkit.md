# T26-02 — Migration verification toolkit

## Что делает

`Migration verification toolkit` формально сравнивает legacy export и новые данные GenomeAI после `T26-01 legacy import adapters`.

Сравнение строится **не по ad hoc скриптам**, а по versioned verification run:

- вход: `artifacts/<data_version>/metadata/legacy_import_bundle.json`
- legacy side: повторная нормализация исходных legacy exports по тем же mapping templates
- new side: canonical CSV или `migration_staging` CSV, созданные import adapters
- выход: `artifacts/<data_version>/migration_verification/<verification_run>/...`

## Что сравнивается

Toolkit сравнивает то, что реально было импортировано/подготовлено к staged adoption:

- `animals`: headcount, active/alive counts
- `lactations`: lactations total, animals with lactations, `avg_milk_305_kg`
- `repro_events`: total events, counts by event type, derived repro statuses (`pregnant/open/bred/other`)
- `treatments`: total treatments, active treatments
- `basic_events` / `health_events`: total events и counts by event type

## Статусы сравнения

Каждая compare-row получает один из bounded статусов:

- `matched` — legacy и new совпали
- `mismatch` — значения различаются
- `manual_review` — метрика недоступна на одной или обеих сторонах, либо нужен ручной разбор

Mismatch **не скрывается** и не агрегируется в “зелёный summary” без детализации.

## Drilldown

Поддерживается drilldown по scope:

- `global`
- `farm`
- `site` (where applicable)
- `group` / `pen` (where applicable)

Если в source или reconciled animal context нет `site_id / pen_id / pen_name`, toolkit честно показывает только доступные уровни.

## Артефакты verification run

Для каждого verification run пишутся:

- `verification_manifest.json`
- `compare_rows.csv`
- `compare_rows.xlsx`
- `dataset_status.csv`
- `issues.csv`

Это делает verification:

- reproducible
- exportable
- пригодным для formal migration sign-off

## Auditability

Если передан `web.db`, run пишет audit event:

- `migration.verification.run`

В audit сохраняются:

- `data_version`
- `verification_run`
- summary
- ссылки на outputs

## Ограничения

- Toolkit не подменяет полноценный reconciliation engine.
- `manual_review` intentionally остаётся явным, если метрика недоступна или контекст неполон.
- Derived repro statuses — bounded operational approximation для migration verification, а не clinical truth engine.
