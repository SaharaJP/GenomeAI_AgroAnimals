# Cow value / culling engine

`T27-01` вводит explainable и economics-transparent decision support по корове.

## Что делает

- считает `value per cow` и `replacement comparison`;
- поддерживает bounded scenarios: `keep / breed / treat / cull / defer`;
- показывает explainable factors и expected economic impact;
- связывает результат с `Animal Profile`, `Operational report builder`, `Decision Log` и `worklists`.

## Принципы

- Никакого автоматического необратимого решения о выбраковке.
- Все economics inputs читаются из versioned config `configs/economics/cow_value_culling_v1.yaml`.
- В UI и в артефактах показываются formulas / assumptions.
- `Cull` всегда требует explicit user confirmation.

## Основные формулы

- `keep_value_rub = (avg_milk_7d * milk_price_per_kg_rub - daily_feed_cost_rub - daily_other_cost_rub) * horizon_days - health_penalty - repro_penalty - parity_penalty`
- `replacement_value_rub = replacement_expected_daily_margin_rub * horizon_days - replacement_purchase_cost_rub + cull_salvage_value_rub - cull_transaction_cost_rub`
- `delta_keep_vs_replace_rub = keep_value_rub - replacement_value_rub`
- `treat_value_rub = keep_value_rub + treatment_recovery_bonus_rub - treatment_followup_cost_rub`
- `breed_value_rub = keep_value_rub + breed_expected_bonus_rub - insemination_cost_rub`
- `defer_value_rub = keep_value_rub - defer_penalty_rub`

## Explainable factors

Минимальный factor set:

- `avg_milk_7d`
- `recent_health_events_30d`
- `active_treatments`
- `latest_scc_cells_ml`
- `repro_state`
- `parity`

Каждый factor показывает:

- значение
- effect direction
- economic effect in RUB
- короткую note/explanation

## Интеграции

### Animal Profile

В summary карточки показывается compact section `Cow value / culling`:

- recommended action
- `Δ vs keep`
- `keep vs replacement`
- `decision required`
- переход в `pages/63_Cow_Value_And_Culling.py`

### Operational report builder

Добавлен report type `cow_value_culling`.

Он показывает:

- `keep_value_rub`
- `replacement_value_rub`
- `delta_keep_vs_replace_rub`
- `recommended_action`
- `expected_impact_rub`

### Decisions / worklists

Поддержаны use-cases:

- `record_cow_value_decision_use_case(...)`
- `create_culling_review_worklist_use_case(...)`

В metadata / why сохраняются:

- engine version
- economics inputs version
- replacement comparison
- linked source facts

## Ограничения

- Это decision support, а не auto-cull executor.
- Формулы intentionally bounded и не претендуют на полную financial model for every farm.
- Если quality/coverage данных ограничены, пользователь видит факторы и assumptions явно, а не скрытый "score".
