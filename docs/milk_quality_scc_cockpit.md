# T27-02 — Milk quality / SCC cockpit

## Что добавлено

`Milk quality / SCC cockpit` — bounded operational cockpit по качеству молока и SCC.

Он не заменяет лабораторную систему и не скрывает quality caveats. Источник расчётов — versioned batch data (`dm_milkings_daily`, `dm_health_events`, `dm_treatments`, current animal context), а economics inputs versioned через `configs/economics/milk_quality_scc_cockpit_v1.yaml`.

## Что считает cockpit

- `estimated_bulk_tank_scc = sum(milk_kg * scc_cells_ml) / sum(milk_kg)` на snapshot date
- `penalty / bonus` по tier schedule `adjustment_rub_per_kg * total_milk_kg`
- animal/group contribution через:
  - `share_of_total_scc_load_pct`
  - `attributed_economic_adjustment_rub`
- action lists по animals и groups

## Quality caveats

Cockpit явно показывает, если:

- отсутствует `dm_milkings_daily`
- часть строк snapshot не содержит `milk_kg` или `scc_cells_ml`
- bulk tank estimate строится только по подмножеству строк

## Связи с operational контуром

- `Animal Profile` → быстрый переход в cockpit
- `Group Profile` → быстрый переход в cockpit
- `Operational report builder` (`milk_quality_watchlist`) → `Open action surface`
- `Daily Worklists` / `Mobile Worklists` для `milk_quality` → открытие cockpit
- из cockpit можно создать `milk_quality` worklist для animal/group

## Ограничения

- Это operational cockpit, а не LIMS.
- bulk tank SCC здесь — reproducible estimate по available batch data, а не обещание лабораторного эталона.
- Penalty/bonus tiers transparent и versioned; никакие economics assumptions не скрываются.
