# Экономика 2.0 (T11-01)

Этот документ описывает витрину **Economics v2** (₽) и правила расчёта.

## Принципы

1) **Offline-core считает, web-cabinet отображает.**
   - расчёт выполняется в модуле `src/genomeai/economics_v2.py` (CLI: `genomeai economics-v2`);
   - UI (Streamlit) запускает пайплайн и читает артефакты из `artifacts/<data_version>/economics_v2/<economics_run>/`.

2) **Все деньги — в рублях (₽).**
   Входные таблицы могут хранить цены/затраты в другой валюте (например EUR), но итоговая витрина всегда в RUB.

3) **Прозрачные формулы.**
   В каждом `economics_run` сохраняется `formulas_catalog.json` и `formula_json` в строках витрины.

## Входные данные (best-effort)

Источник: `artifacts/<data_version>/canonical/*.csv`.

Минимальный набор (для базовой маржи):

- `dm_milkings_daily` — удой по дням (используется `milk_kg`).
- `dm_feed_deliveries` — выдача кормов (используется `as_fed_kg`).
- `dm_feed_rations` — параметры рациона (используется `dm_pct` — доля сухого вещества).
- `dm_economics_daily` — цены/затраты на день (milk/feed/other). Валюта по умолчанию задаётся в конфиге.

Расширения (категории расходов/доходов):

- `dm_treatments` — события лечения (для vet‑затрат; упрощённо «стоимость на событие»).
- `dm_repro_events` — репро‑события (для затрат на осеменения; упрощённо «стоимость на событие»).
- `dm_cull_events` — выбраковка/реализация (выручка/затраты из полей или по умолчанию из конфига).

> Если каких-то таблиц нет — расчёт продолжает работать (best-effort) и подставляет значения по умолчанию, а источники/доверие отражаются в `sources_json`.

## Конфигурация

Путь по умолчанию: `configs/economics/economics_v2.yaml`.

Ключевые параметры:

- `output.currency`: всегда `RUB`.
- `fx_rates`: курсы валют к RUB.
- `defaults.milk_price / feed_cost / other_cost`: дефолты, если входных цен нет.
- `cost_models.vet / repro / cull`: упрощённые модели затрат/доходов (стоимость на событие / на голову).
- `allocation.other_cost_allocation`: как распределять `other_cost` по pen (по доле выручки).

## Выходные артефакты

Путь:

`artifacts/<data_version>/economics_v2/<economics_run>/`

Файлы:

1) `economics_daily.csv`
   - гранулярность: `level ∈ {pen, site, farm}` × `date`.
   - ключи: `tenant_id, farm_id, site_id, pen_id, date`.

2) `economics_monthly.csv`
   - гранулярность: `level` × `YYYY-MM`.

3) `formulas_catalog.json`
   - каталог формул и параметров (currency=RUB, cost_models, правила агрегации).

4) `manifest.json`
   - метаданные запуска: `data_version`, `economics_run`, `date_from/date_to`, ссылки на входные таблицы.

## Основные показатели и формулы

На уровне **pen** (строки daily):

- `revenue_milk_rub = milk_kg * milk_price_rub_per_kg`
- `cost_feed_rub = feed_dm_kg * feed_cost_rub_per_kg_dm`
- `cost_vet_rub = treatments_n * vet_cost_per_treatment_event_rub`
- `cost_repro_rub = inseminations_n * insemination_cost_rub`
- `revenue_cull_rub / cost_cull_rub`:
  - если есть `dm_cull_events.revenue_rub/cost_rub` → суммируем,
  - иначе `cull_events_n * (revenue_per_head_rub / cost_per_head_rub)`.
- `cost_other_rub` — распределение `other_cost` по правилам `allocation`.
- `total_cost_rub = cost_feed_rub + cost_vet_rub + cost_repro_rub + cost_cull_rub + cost_other_rub`
- `margin_rub = revenue_total_rub - total_cost_rub`
- `cost_per_liter_rub = total_cost_rub / milk_liters`

На уровнях **site/farm**:

- агрегация — `SUM` по дочерним строкам.

## Проверка

1) Unit-tests:

```bash
pytest -q tests/test_t11_01_economics_v2.py
```

2) Ручной прогон:

```bash
genomeai economics-v2 --data-version dv_demo --date-from 2025-01-01 --date-to 2025-01-31
npm --prefix web_app run start
```

Откройте страницу **«Экономика 2.0 (T11-01)»** и проверьте: суммы в ₽, таблицу daily/monthly, «расшифровку формул».
