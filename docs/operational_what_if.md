# T27-05 — Explainable operational what-if

## Что это

`Operational what-if` — это bounded слой для herd manager, который переносит what-if из director-only режима в daily execution.

Он не подменяет текущий strategic what-if backend и не делает новых тяжёлых вычислений в UI.
Он использует уже существующие operational/economics engines и показывает по конкретному объекту или worklist:

- сравнение сценариев;
- expected gain / loss;
- cost of delay;
- expected ROI;
- uncertainty / caveats;
- linked source facts.

## Поддерживаемые scenario families

- `cull_keep`
- `treat_protocol`
- `repro_priority`
- `group_move`
- `milk_quality_protocol`
- `fresh_transition`
- `reprioritize`

## Источники

Слой строится поверх:

- `cow_value_culling_v1`
- `economics_per_action_v1`
- `milk_quality_scc_cockpit_v1`
- `fresh_cows_transition_economics_v1`

## Что сохраняется

При создании решения из what-if сохраняются:

- `scenario_family`
- `selected_scenario`
- `recommended_scenario_key`
- `economics_inputs_version`
- `source_engine`
- `source_versions`
- `linked_source_facts`
- `worklist_id` (если сценарий открыт из worklist)

## Что deliberately не делаем

- не ломаем существующий strategic what-if backend;
- не скрываем uncertainty;
- не делаем analyst-only DSL;
- не делаем автоматическое необратимое действие.

## Основные surfaces

- `pages/67_Operational_What_If.py`
- `Animal Profile`
- `Group Profile`
- `Daily Worklists`
- `Mobile Worklists`
- `Operational Report Builder`

## Acceptance

Herd manager видит practical compare сценариев прямо в operational контуре и может:

- понять экономический смысл действия;
- увидеть assumptions/caveats;
- экспортировать compare;
- создать decision или follow-up worklist без потери контекста.
