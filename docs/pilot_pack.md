# Pilot Pack (A6)

Pilot Pack — это единый пакет артефактов для передачи заказчику.

## Что входит

Структура папки `artifacts/<data_version>/pilot_packs/<pack_id>/`:

- `canonical/` — канонические таблицы (CSV/Parquet)
- `qc/` — QC отчёт и bad_rows
- `models/` — модель (joblib) + model card
- `scoring/` — результаты скоринга + экспорты (xlsx)
- `reports/` — отчёт (docx/pdf) + fact_pack
- `decisions/` — decision_log (csv/xlsx/jsonl)
- `metadata/` — снимок метаданных (summary json)
- `versions.json` — связка версий data/qc/model/scoring/report
- `pack_manifest.json` — sha256 для всех файлов в пакете
- `pilot_pack_summary.json` — итоговая карточка пакета

## decision_log

Объект решения: `animal_id + lactation_id + recommendation_type`.

Минимальные поля:

- `animal_id`
- `lactation_id` (в P0 это surrogate `animal_id__lactation_no`)
- `recommendation_type` (например, PRIORITY/OBSERVE/CULL_CANDIDATE)
- `decision` (например, ACCEPT/REJECT/DEFER)
- `comment`
- `user`
- `created_at_utc`

## Команды

Создать шаблон decision log из скоринга:

```bash
genomeai decision init --data-version <dv> --scoring-run <sr> --user "Ivan"
```

Добавить запись решения:

```bash
genomeai decision add --data-version <dv> --animal-id A1 --lactation-id A1__1 \
  --recommendation-type PRIORITY --decision ACCEPT --comment "Проверить корм" --user "Ivan"
```

Собрать Pilot Pack:

```bash
genomeai pack --data-version <dv> --qc-run <qr> --model-version <mv> --scoring-run <sr> --report-version <rv>
```
