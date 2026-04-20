# KPI-словарь директора v2 (Target)

Этот документ описывает KPI v2 для “кабинета руководителя” (уровень фермы).  
KPI **воспроизводимы**: считаются модулем `src/genomeai/kpi_v2.py` и трассируются через `data_version` и `run_id`.

## Как посчитать
```bash
genomeai kpi --data-version <dv> --asof-date 2025-01-05 --input-dir data/fixtures/target_v2 --artifacts artifacts
```

Выход:
- `artifacts/<dv>/runs/<kpi_run>/kpi/kpi_long.csv`
- `artifacts/<dv>/runs/<kpi_run>/kpi/kpi_wide.csv`
- `artifacts/<dv>/runs/<kpi_run>/kpi/kpi_alerts.csv`
- `artifacts/<dv>/runs/<kpi_run>/run_manifest.json`
- `artifacts/<dv>/runs/<kpi_run>/checksums.json`

## Валюта и FX
KPI экономики выводятся в **RUB**.  
Если источники в EUR, применяется фиксированный коэффициент `EUR_RUB` из `configs/kpi/kpi_thresholds_v2.yaml`.

## KPI (25)
Источником правды для списка KPI является `configs/kpi/kpi_v2.yaml`. Ниже — кратко.

### Молоко
- `milk_total_kg_1d/7d/30d` — сумма `dm_milkings_daily.milk_kg` за период
- `milk_avg_kg_per_cow_1d` — `milk_total_kg_1d / active_cows`
- `fat_pct_avg_7d` — средневзвешенное по `milk_kg`
- `protein_pct_avg_7d` — средневзвешенное по `milk_kg`
- `scc_avg_7d` — среднее `scc_cells_ml`

### Здоровье
- `health_events_30d` — количество `dm_health_events`
- `mastitis_events_30d` — события, где `event_type` содержит “mast”
- `severe_health_events_30d` — severity ∈ {major,severe,critical}

### Сенсоры
- `activity_avg_7d` — среднее `activity_count`
- `rumination_avg_7d` — среднее `rumination_min`
- `temperature_avg_7d` — среднее `temperature_c`

### Репродукция
- `inseminations_30d` — `event_type` содержит “insemin”
- `pregnancy_positive_90d` — `result` ∈ {pregnant,positive,yes}
- `calvings_90d` — количество `dm_lactations` по `calving_date`

### Кормление
- `feed_as_fed_kg_7d` — сумма `dm_feed_deliveries.feed_kg_as_fed`
- `feed_dm_kg_7d` — `feed_kg_as_fed * dm_pct/100`
- `feed_dm_kg_per_cow_7d` — `feed_dm_kg_7d / active_cows / 7`

### Экономика (RUB)
- `milk_revenue_rub_7d` — `milk_kg_7d * milk_price_per_kg * EUR_RUB`
- `feed_cost_rub_7d` — `feed_dm_kg_7d * feed_cost_per_kg_dm * EUR_RUB`
- `other_cost_rub_7d` — `sum(other_cost_eur) * EUR_RUB`
- `margin_rub_7d` — revenue - feed - other

### Алерты/решения
- `alerts_open_count` — количество `dm_alerts` со статусом `open`
- `decisions_accept_rate_90d` — доля `accept` в `dm_decisions` за 90 дней

## Красные зоны (thresholds) и Alerts
Пороги и маппинг KPI→Alert задаются в `configs/kpi/kpi_thresholds_v2.yaml`.  
Политика: **blocker только алерты** — расчёт KPI не блокируется, создаются записи в `kpi_alerts.csv`.
