# Миграция Offline → Mini‑Web → Web Cabinet

Документ описывает, как мигрируем продукт от офлайн‑пайплайна (CLI) к мини‑кабинету, а затем к полноценному кабинету.

## Принципы

### Разделение слоёв
- **offline-core (`src/genomeai`)**: расчёты, ML, QC, отчёты, версионирование.
- **web-cabinet (`web_cabinet`)**: UI + оркестрация (джобы/логи), веб **не считает**.

### Единый контракт версий
Сквозные версии (ID) не генерируются вебом и всегда фиксируются в артефактах:

- `data_version`
- `qc_run`
- `model_version`
- `scoring_run`
- `report_version`
- `decision_log`

## Этапы

### Этап A: Offline (CLI)
**Артефакты храним локально** (on‑prem) в `artifacts/`.

Команды (пример):
- `genomeai ingest ...`
- `genomeai qc ...`
- `genomeai train ...`
- `genomeai score ...`
- `genomeai report ...`
- `genomeai pack ...`

Передача между средами/инсталляциями делается через **Pilot Pack** (zip).

### Этап B: Mini‑Web
Цель — минимальный кабинет:

- загрузка файлов;
- запуск джобов (subprocess) с таймаутами;
- просмотр логов;
- скачивание результатов;
- health/ready/metrics для ops.

### Этап C: Полноценный Web Cabinet
Цель — роли и операционка:

- RBAC;
- Audit Log;
- Alert Center / Tasks;
- Decision Log (append‑only);
- Observability.

## Переносимость артефактов

### Формат переносимости: Pilot Pack
Pilot Pack — zip с:

- `versions.json` (обязателен)
- `pack_manifest.json` (опционально, sha256)
- папки: `canonical/`, `qc/`, `models/`, `scoring/`, `reports/`, `decisions/`, `metadata/`

### Импорт в Target layout
Используем команду:

```bash
python -m genomeai import-pack --pack-zip <path/to/pack.zip> --artifacts artifacts
```

Импортёр раскладывает слои в `artifacts/<data_version>/...` и пишет `artifacts/<dv>/imports/<pack_id>/import_manifest.json`.

## Совместимость версий

Минимальный контракт для импорта:
- ключи в `versions.json`: `data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`

Совместимость вперёд:
- новые файлы могут добавляться в pack без поломки импорта;
- критические изменения — только через новую схему (`...v2`) + backward‑compat в импортёре.

## Smoke tests миграции

Команда для end‑to‑end проверки:

```bash
python -m genomeai smoke-migration --artifacts artifacts
```

Что делает:
1) строит офлайн артефакты и Pilot Pack во временной папке;
2) импортирует pack в указанный `artifacts/`.

Ожидаемый результат: `SMOKE_MIGRATION_OK` и `import_manifest_json` в выводе.
