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
