# T26-01 — Legacy import adapters / migration templates

## Что добавлено

Введён bounded слой `core.interoperability.legacy_import` для загрузки типовых legacy herd-management exports **поверх текущего ingest pipeline**, без отдельного параллельного импортёра.

Поддержаны три template families:

- `generic_hms_csv_bundle`
- `dairycomp_305_basic`
- `selex_basic`

Поддержанные dataset groups:

- `animals`
- `lactations`
- `treatments`
- `repro_events`
- `basic_events`

## Как это работает

### 1. Canonical import where possible

Для `animals`, `lactations`, `treatments` и `health_events` используется **тот же текущий contract-based ingest**, что и для остальных данных системы:

- `genomeai.contract_precheck.validate_source_by_contract(...)`
- `genomeai.ingest.ingest_dataset(...)`

Это сохраняет совместимость с current ingest/QC/versioning path.

### 2. Stage-only import for legacy operational exports

Для `repro_events` и `basic_events` rows не пишутся напрямую в append-only runtime tables.

Вместо этого создаются:

- `artifacts/<data_version>/migration_staging/<dataset>.csv`
- `artifacts/<data_version>/migration_staging/<dataset>_operational_preview.jsonl`

Это deliberate bounded behavior:

- не обещается «идеальная миграция без reconciliation»;
- staged adoption возможен до full cutover;
- runtime event integrity не ломается.

## Diagnostics / QC mapping issues

`preview_legacy_mapping_diagnostics(...)` показывает explainable mapping issues:

- missing source column
- duplicate target mapping
- required field not mapped
- coercion failed
- required field empty
- unused source column
- bounded event-type normalization warnings

Итоговый bundle summary пишет:

- per-dataset diagnostics
- quality / reconciliation summary
- staged adoption plan
- явные assumptions

## Staged adoption

`build_legacy_import_plan(...)` формирует практический phased path:

1. `stage_1_master_data` — animals + lactations
2. `stage_2_reproduction` — repro events
3. `stage_3_treatments` — treatments
4. `stage_4_basic_events` — basic operational events

Это позволяет заводить данные частями, а не только full cutover.

## Deliverables

- `src/core/interoperability/legacy_import.py`
- `src/core/interoperability/__init__.py`
- `configs/mappings/legacy/*`
- `scripts/smoke_t26_01_legacy_import_adapters.py`
- `tests/test_t26_01_legacy_import_adapters.py`

## Как проверить

```bash
PYTHONPATH=src:. python scripts/smoke_t26_01_legacy_import_adapters.py

PYTHONPATH=src:. pytest -q tests/test_t26_01_legacy_import_adapters.py
```

## Ограничения

- Это не universal reconciliation engine.
- `repro_events` и `basic_events` в этой итерации импортируются в **staging + preview**, а не прямо в runtime event tables.
- Unknown legacy event semantics не исполняются автоматически; они bounded и явно помечаются в diagnostics.
