# Unit economics (T11-03)

Витрина «вклад животного/группы в прибыль» (доход − расход).

**Важно:** в текущей версии (v1) это attribution/allocations на базе `economics_v2` и событий, а не доказанная причинность.

## Выходные файлы

`artifacts/<data_version>/unit_economics/<unit_econ_run>/`
- `unit_economics_animal_daily.csv`
- `unit_economics_group_daily.csv`
- `manifest.json`

Также копия в формате Target run layout:
`artifacts/<data_version>/runs/<unit_econ_run>/unit_economics/*`

## unit_economics_animal_daily.csv

Grain: `tenant_id, animal_id, date` (animal-day)

Колонки (минимум):
- `tenant_id`
- `animal_id`
- `date`
- `farm_id`, `site_id`, `pen_id` — назначение группы (best-effort)
- `milk_kg`
- `revenue_milk_rub`, `revenue_cull_rub`, `revenue_total_rub`
- `cost_feed_rub`, `cost_other_rub`, `cost_vet_rub`, `cost_repro_rub`, `cost_cull_rub`, `total_cost_rub`
- `margin_rub`
- `economics_run` — источник pen-day экономики

## unit_economics_group_daily.csv

Grain: `tenant_id, level, (farm/site/pen ids), date`.

- `level`: `pen|site|farm`
- Метрики: суммы по животным за день (см. набор колонок выше)

## manifest.json

- `data_version`, `unit_econ_run`, `economics_run`
- `date_from`, `date_to`
- `allocation` — метод распределения
- `cost_models` — тарифы для vet/repro
- `limitations` — список дисклеймеров

## Allocation methodology (RFC §4.5 gap closure)

Источник правды реализации: `src/genomeai/unit_economics.py::run_unit_economics` (поле `allocation.cost_method` из `configs/economics/unit_economics_v1.yaml`).

В витрине pen-day (выход `economics_v2`) три позиции являются **pooled** на уровне загона и распределяются на животных по share-фактору. Три позиции являются **direct** (per-event) и относятся напрямую на конкретное животное без аллокации.

| Колонка pen-day | Природа | Куда уходит при animal-day |
|---|---|---|
| `revenue_milk_rub` | pooled (мерили на pen-day) | `revenue_milk_rub_alloc = revenue_milk_rub * share` |
| `cost_feed_rub` | pooled | `cost_feed_rub_alloc = cost_feed_rub * share` |
| `cost_other_rub` | pooled (other_cost_rub_per_farm_day, аллоцирован пенам в economics_v2) | `cost_other_rub_alloc = cost_other_rub * share` |
| `revenue_cull_rub` | direct (per cull event) | `cull_event.revenue_rub` (или дефолт из config) → конкретное животное |
| `cost_cull_rub` | direct (per cull event) | `cull_event.cost_rub` (или дефолт) → конкретное животное |
| `cost_vet_rub` | direct (per treatment event) | `treatments_n_animal × vet_cost_per_treatment_event_rub` |
| `cost_repro_rub` | direct (per insemination) | `inseminations_n_animal × insemination_cost_rub` |

### share-фактор

Два метода (configurable via `allocation.cost_method`):

**`milk_share`** (default):

```
pen_milk_kg = SUM(milk_kg) per (tenant_id, pen_id, date)
share = milk_kg / pen_milk_kg                            # для каждого animal-day
```

При `pen_milk_kg == 0` (нет надоев в пене за день) `share = 0` — pool не аллоцируется. Это «no-milk-no-revenue» semantics: животное, не давшее молока в этот день, не претендует на долю в надойной выручке/корме/прочих pooled-расходах.

**`headcount`** (v1 approximation):

```
pen_animals_n = COUNT DISTINCT(animal_id) per (tenant_id, pen_id, date) среди тех, у кого был milking record
share = 1 / pen_animals_n
```

Равная доля между всеми животными пена с записанным milking-событием за день. Не пытается учитывать сухостой / технологические группы — это v2-задача.

### Invariants

- `SUM(share) per (tenant, pen, date) ∈ [0, 1]` — может быть < 1, если у части животных не было milking записи (потеряли долю).
- `SUM(revenue_milk_rub_alloc) per pen-day ≤ revenue_milk_rub pen-day` — round-trip сохраняется только при полном покрытии milking-фактом.
- Direct-расходы (vet/repro/cull) суммируются на animal-day по событиям; их сумма по пену равна `cost_vet_rub + cost_repro_rub + cost_cull_rub` на pen-day только при равенстве тарифов в `cost_models`.

### Known limitations (v1)

- Не учитывает сухостойных коров без milking-events — они получат `share = 0` и нулевую долю pooled-выручки/расхода. Это смещение для farms с большой долей сухостоя.
- Не учитывает разную продуктивность тёлок vs опытных коров в headcount-режиме — равная доля по всем животным.
- Не моделирует индивидуальные feed-conversion-rates — `cost_feed` распределяется по milk-output proportionально, что приближает реальность только при сходных рационах.
- v2 roadmap: per-cow feed allocation на основе real ration data + body weight, individual cull NPV-based attribution.
