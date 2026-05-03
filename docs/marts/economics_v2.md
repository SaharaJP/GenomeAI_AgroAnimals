# Mart: economics_v2

Март **economics_v2** — это витрина доходов/расходов/маржи в ₽ на уровне:

- `farm` (ферма)
- `site` (площадка)
- `pen` (группа/секция)

Витрина строится в **offline-core** (CLI: `genomeai economics-v2`) и сохраняется в артефакты конкретного запуска:

`artifacts/<data_version>/economics_v2/<economics_run>/`

## economics_daily.csv

Гранулярность: `level × date`.

Ключевые поля:

- `level`: `pen|site|farm`
- `tenant_id`
- `farm_id`, `site_id`, `pen_id`
- `date`

Поля объёма:

- `milk_kg`, `milk_liters`
- `feed_as_fed_kg`, `feed_dm_kg`

Доходы (₽):

- `revenue_milk_rub`
- `revenue_cull_rub`
- `revenue_total_rub`

Расходы (₽):

- `cost_feed_rub`
- `cost_vet_rub`
- `cost_repro_rub`
- `cost_cull_rub`
- `cost_other_rub`
- `total_cost_rub`

Итоги (₽):

- `margin_rub`
- `margin_pct`
- `cost_per_liter_rub`

Прозрачность и источники:

- `sources_json`: какие таблицы/поля использовались, что было пропущено, что заполнено default-ами
- `formula_json`: фактическая подстановка параметров и формул (для pen и агрегатов)

## economics_monthly.csv

Гранулярность: `level × month (YYYY-MM)`.

- `month`: период
- остальные поля аналогичны `economics_daily`, но агрегированы суммами.

## Связанные артефакты

- `formulas_catalog.json`: каталог формул и параметров cost_models
- `manifest.json`: метаданные запуска и привязка к `data_version`

## Примечания

1) **Витрина best-effort**: если каких-то входных таблиц нет, строки не падают и заполняются `NA` или дефолтами из `configs/economics/economics_v2.yaml`.
2) Все суммы и показатели в витрине — в **₽ (RUB)**.
