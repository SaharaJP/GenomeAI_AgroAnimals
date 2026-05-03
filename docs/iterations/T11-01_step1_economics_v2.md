# T11-01 (step1): Экономика 2.0 — витрина в рублях + UI страница

## Что добавлено

1) **Offline-core витрина** `economics_v2`:
   - Генерация `economics_daily.csv` и `economics_monthly.csv` в RUB.
   - Прозрачные формулы: `formulas_catalog.json` + `formula_json`/`sources_json` в строках.
   - Версионирование: `data_version` + `economics_run`.

2) **CLI команда**:
   - `python -m genomeai economics-v2 ...`

3) **Web-cabinet (Streamlit) страница**:
   - `Экономика 2.0 (T11-01)` в навигации.
   - Запуск пайплайна (требует `pipeline.run`), просмотр витрины и расшифровка формул.
   - Экспорт артефактов с записью в audit log.

## Входные данные (каноника Target v2)

Ожидаемые таблицы (CSV/Parquet) из `artifacts/<data_version>/canonical`:

- `dm_milkings_daily` (milk_kg)
- `dm_feed_deliveries` + `dm_feed_rations` (feed_dm_kg)
- `dm_economics_daily` и/или `dm_prices` (цены/ставки)
- `dm_treatments` (вет-операции)
- `dm_repro_events` (осеменения)
- `dm_pens`, `dm_sites`, `dm_pen_moves` (для распределения по группам)

## Конфиг

`configs/economics/economics_v2.yaml`:

- курсы FX (по умолчанию `EUR=100`, `USD=90`)
- дефолтные ставки (если таблиц/полей нет)
- модель распределения `other_cost_per_farm_day` по группам

## Как запустить

### CLI

```bash
python -m genomeai economics-v2 \
  --data-version dv_demo \
  --date-from 2025-01-01 \
  --date-to 2025-01-31
```

### Streamlit

Открыть страницу **💸 Economics 2.0** и нажать **«Посчитать витрину»**.
