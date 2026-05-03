# Data Versioning Spec (Target) — data_version + run_id + re-run

> Цель: обеспечить **сквозную трассируемость** любых результатов (QC/ML/скоринг/отчёты/алерты/решения) до:
> - версии данных (**data_version**)
> - запуска вычисления (**run_id**)
> - входных артефактов и настроек (lineage / manifests)
>
> Документ задаёт **поведение и контракты**, без привязки к конкретному хранилищу (ФС/S3/DB).

## 1. Термины и идентификаторы

### 1.1 data_version (версия данных)
**data_version** — неизменяемая (immutable) версия *канонического* датасета, используемая во всех вычислениях.

**Свойства:**
- **deterministic**: может быть пересчитана как hash(manifest) канонических файлов.
- **immutable**: данные внутри data_version **не перезаписываются**, только добавляются новые версии.
- **addressable**: любой артефакт/результат хранит ссылку на `data_version`.

**Рекомендуемый формат (человекочитаемый):**
- `dv_<YYYYMMDD>_<HHMMSS>_<short_hash>`
- пример: `dv_20251230_142530_a1b2c3`

> В MVP уже используется `data_version` как папка в `artifacts/<data_version>/...`.
> Target сохраняет обратную совместимость: старый формат допустим.

### 1.2 run_id (запуск вычисления)
**run_id** — идентификатор конкретного запуска вычисления/построения артефактов (QC, train, score, report, alerts, dashboard materialization и т.д.).

**Свойства:**
- уникален в пределах `data_version`
- имеет тип запуска (`run_type`)
- хранит ссылки на входные run_id (lineage)
- хранит code/config/env fingerprints для воспроизводимости

**Рекомендуемый формат:**
- `<run_type>_<YYYYMMDD>_<HHMMSS>_<rand6>`
- примеры:
  - `qc_20251230_143001_k3p9az`
  - `train_20251230_143520_j7d1qv`
  - `score_20251230_144010_0x9m2b`
  - `report_20251230_144330_f8c2aa`

### 1.3 Версии моделей/отчётов (model_version/report_version)
В Target рекомендуется **унифицировать**: `model_version` и `report_version` — это частные случаи `run_id` (типа `train`, `report`).
Но для совместимости можно сохранять текущие имена, при этом в manifest всегда есть:
- `run_id`
- `legacy_id` (опционально): `model_version`, `report_version`, `qc_run`, `scoring_run`

## 2. Инварианты и требования (обязательные правила)

### 2.1 Ничего “тихо не исправляем”
- Любое изменение данных/решений — новый `data_version` или новый `run_id`.
- Любая коррекция/дедуп/merge — фиксируется в **audit_log** и/или **lineage events**.

### 2.2 Любой результат трассируется
Каждый артефакт MUST иметь manifest/metadata, содержащий минимум:
- `data_version`
- `run_id`
- `run_type`
- `created_at` (UTC ISO-8601)
- `created_by` (user/service)
- `inputs` (перечень входных артефактов/версий)
- `code_fingerprint` (git_sha или image_tag)
- `config_fingerprint` (hash конфигов/параметров)
- `artifacts_manifest` (список файлов с sha256)

### 2.3 Иммутабельность и append-only
- Внутри `artifacts/<data_version>/...` **нельзя** перезаписывать файлы предыдущих run.
- Разрешены только новые папки `run_id` и новые manifests.

### 2.4 Idempotency (там, где возможно)
Если запуск выполнен повторно с теми же входами/конфигами/кодом, допустимы два режима:
- **strict**: запретить запуск и вернуть уже существующий `run_id` (по hash-подписи).
- **append**: разрешить новый `run_id`, но manifest помечает `rerun_of=<old_run_id>`.

Для MVP/Target рекомендуется **append** (проще для аудита).

## 3. Структура артефактов

### 3.1 Нормативная структура Target
Базовая структура (логическая, может быть реализована на ФС/объектном хранилище/DB):

```
artifacts/
  <data_version>/
    canonical/                       # каноника (таблицы v1/v2)
      dm_farms.(csv|parquet)
      dm_animals.(csv|parquet)
      dm_lactations.(csv|parquet)
      ...
      canonical_manifest.json        # sha256, rowcounts, schema refs

    runs/
      <run_id>/                      # универсальная папка запуска
        run_manifest.json            # обязательный manifest
        logs/                        # stdout/stderr, structured logs
        outputs/                     # выходы запуска (xlsx, models, csv)
        metrics/                     # json метрики
        lineage/                     # входы/ссылки/graph export (optional)

    indexes/                         # удобные "указатели" (optional)
      latest_qc -> runs/qc_.../
      latest_train -> runs/train_.../
      latest_score -> runs/score_.../
      ...

    legacy/                          # совместимость с MVP (optional)
      qc/<qc_run>/...
      models/<model_version>/...
      scoring/<scoring_run>/...
      reports/<report_version>/...
```

**Пояснение про legacy:** Target допускает хранение результатов как сейчас в MVP (qc/models/scoring/reports),
но **нормативно** всё также описывается через `runs/<run_id>/run_manifest.json`.

### 3.2 Минимальный run_manifest.json (пример)
```json
{
  "schema_version": "run_manifest_v1",
  "run_id": "score_20251230_144010_0x9m2b",
  "run_type": "score",
  "created_at_utc": "2025-12-30T14:40:10Z",
  "created_by": {"user": "operator", "role": "Operator"},
  "data_version": "dv_20251230_142530_a1b2c3",
  "inputs": {
    "qc_run_id": "qc_20251230_143001_k3p9az",
    "train_run_id": "train_20251230_143520_j7d1qv"
  },
  "code_fingerprint": {"git_sha": "abc1234", "image": "genomeai:1.3.0"},
  "config_fingerprint": {"sha256": "9e1f..."},
  "artifacts_manifest": [
    {"path": "outputs/animal_ranking.xlsx", "sha256": "..." },
    {"path": "outputs/group_summary.xlsx", "sha256": "..." }
  ]
}
```

### 3.3 canonical_manifest.json (пример)
```json
{
  "schema_version": "canonical_manifest_v1",
  "data_version": "dv_20251230_142530_a1b2c3",
  "created_at_utc": "2025-12-30T14:25:30Z",
  "tables": [
    {
      "name": "dm_animals",
      "path": "canonical/dm_animals.csv",
      "sha256": "...",
      "rows": 12034,
      "contract_ref": "configs/contracts/dm_animals.json"
    }
  ]
}
```

## 4. Re-run (воспроизведение) по версии

### 4.1 Что значит re-run
Re-run — это воспроизведение результата **на той же версии данных** (`data_version`), с фиксированными входами и конфигами, чтобы получить:
- тот же отчёт (fallback/LLM),
- тот же набор таблиц/дашборд-материализаций,
- тот же скоринг и агрегаты (при одинаковом коде/модели).

### 4.2 Режимы re-run
**R1: replay artifacts (preferred)**  
Если нужный `run_id` уже существует, UI/CLI просто повторно отдаёт эти артефакты (без вычислений).

**R2: rerun compute (deterministic attempt)**  
Создаётся новый `run_id`, но:
- `rerun_of=<old_run_id>` в manifest
- используются те же входы:
  - для report: тот же `scoring_run_id`, `model_run_id`, `qc_run_id`
  - для score: тот же `train_run_id` (модель), та же каноника
- конфиги берутся по `config_fingerprint` из исходного run_manifest (или явной ссылке на конфиг-файл, сохранённой в папке run).

### 4.3 Что должно быть зафиксировано для воспроизводимости
Для каждого run MUST сохраняться:
- **input references** (какие dv/run_id использовались)
- **code_fingerprint** (git_sha / image)
- **config snapshot** (копия yaml/json параметров или их hash + путь)
- **random seeds** (если применимо)
- **dependency fingerprint** (optional): `pip freeze`/`poetry.lock` hash

### 4.4 Поведение UI/CLI “re-run report”
UI/CLI получает:
- `data_version`
- `report_run_id` (или комбинацию dv+qc+train+score)
и делает:
1) если `report_run_id` существует → R1 (replay artifacts)  
2) иначе → создаёт новый `report_<...>` и запускает генерацию отчёта с теми же inputs (R2)

## 5. Примеры согласованных версий (сквозная трасса)

### 5.1 Пример полного цикла
- `data_version = dv_20251230_142530_a1b2c3`
- QC: `qc_20251230_143001_k3p9az`
- Train: `train_20251230_143520_j7d1qv` (model artifact)
- Score: `score_20251230_144010_0x9m2b`
- Report: `report_20251230_144330_f8c2aa`

Требование: в `report` manifest есть ссылки на **qc/train/score** + `data_version`.

### 5.2 Пример структуры папок (Target)
```
artifacts/dv_20251230_142530_a1b2c3/
  canonical/...
  runs/
    qc_20251230_143001_k3p9az/...
    train_20251230_143520_j7d1qv/...
    score_20251230_144010_0x9m2b/...
    report_20251230_144330_f8c2aa/...
```

## 6. Совместимость с MVP (важно)
MVP уже использует:
- `data_version`
- `qc_run`, `model_version`, `scoring_run`, `report_version`

Target-спека **не ломает** это:
- текущие пути допустимы как `legacy/`
- любой run MUST иметь `run_manifest.json` (можно генерировать и для legacy запусков постфактум)

## 7. Минимальные проверки целостности (для Target)
Для каждого `run_id` минимально проверяем:
- manifest валиден и содержит `data_version`, `run_id`, `run_type`
- все `artifacts_manifest[].path` существуют (или доступны по backend)
- sha256 совпадает (опционально: full verify в фоне/по запросу)
- `inputs` указывают на существующие run_id в рамках dv (или внешние ссылки)

---

## Appendix A — Naming conventions
- Все таблицы/сущности: `snake_case`, префикс `dm_` для канонических таблиц.
- Идентификаторы: `*_id`, строковые (alphanumeric), стабильно сравнимые.
- Даты: ISO `YYYY-MM-DD`, время: `YYYY-MM-DDTHH:MM:SSZ` (UTC).

## Appendix B — Единицы измерения (ключевые)
- молоко: `kg` (предпочтительно) или `l` с явным флагом плотности/конвертацией
- температура: `C`
- активность: `index` (безразмерный) или `steps` (если шаги)
- корма: `kg_as_fed`, `kg_dm` (dry matter) — явно в поле `unit`


## Implementation in current MVP/Target code

- Run folder layout is materialized for QC/Train/Score/Report runs under `artifacts/<data_version>/runs/<run_id>/`.
- Each run folder includes:
  - `run_manifest.json` (step, lineage, outputs)
  - `checksums.json` (sha256 for files under run subdir)
- Legacy folders (`qc/`, `models/`, `scoring/`, `reports/`) remain for backward compatibility; run manifests reference both.

### Reproduce / replay

Command:

```bash
genomeai run reproduce --data-version <dv> --run-id <report_run_id>
```

- If the source run is a **report** and lineage is available, it will **re-run** the report in fallback mode.
- Otherwise it will **replay** (copy) the stored run folder into a new `reproduce_*` run.
