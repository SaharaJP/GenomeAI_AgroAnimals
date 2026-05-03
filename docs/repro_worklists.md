# Repro worklists

T22-02 добавляет operational surface для специалиста по воспроизводству без отдельной repro task model.

## Что считается

Списки due actions строятся в `core.reproduction.worklists` из `reproduction.state_machine`:
- `watch_heat`
- `inseminate`
- `preg_check`
- `recheck`
- `dry_off`

Источник истины для статуса животного — `compute_reproduction_state(...)` / `build_reproduction_states_table(...)`.
UI только отображает snapshot и вызывает общие use-cases.

## Materialize в worklists

Derived due actions можно materialize в обычные `worklists` типа `reproduction` через `sync_reproduction_worklists_use_case(...)`.

- storage: `tasks_v1`
- dedupe: `repro:<action_type>:<animal_id>:<due_date>`
- owner/team: `team-repro`
- linked facts: source facts из repro state machine

## Completion / comments

- batch completion: через общий outcome loop `record_completion_outcome_use_case(...)`
- bulk comments: через append-only `animal_event.quick_entry.comment`

## UI

Основная страница: `pages/45_Reproduction_Worklists.py`

Поддержано:
- фильтры по `animal_id`, `pen_id`, `action_type`
- source facts / due / confidence / expected effect
- переходы в `Animal Profile` и `Group Profile`
- materialize selected actions
- batch complete materialized worklists
- bulk comments по выбранным животным
