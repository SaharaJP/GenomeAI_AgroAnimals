# Reproduction state machine

T22-01 фиксирует reproduction lifecycle как детерминированный core-layer, а не как UI-эвристику.

## Состояния

- `eligible`
- `heat`
- `bred`
- `preg_check_due`
- `pregnant`
- `open`
- `repeat`
- `fresh`
- `dry`
- `cull_candidate`

## Источники переходов

State machine использует только воспроизводимые source facts:

- `dm_repro_events`
- `dm_lactations` (`calving_date`, `dryoff_date`)
- `dm_animals.status`
- append-only `animal_events_v1` для manual/operational repro events

## Базовые правила

- `calving` → `fresh`
- после `fresh`/VWP без сервиса → `eligible`
- `heat` → `heat`
- `insemination` → `bred`
- после `insemination` и наступления срока проверки → `preg_check_due`
- positive `preg_check` → `pregnant`
- negative `preg_check` после первого сервиса → `open`
- negative `preg_check`/повторные сервисы → `repeat`
- `dry_off` → `dry`
- `cull`/`death`/status=`culled|dead` → `cull_candidate`

## Где показывается

- `Animal Profile`: текущий `Reproduction state`
- `Group Profile`: roster и group worklists по `repro_state_label/repro_reason_label`
- `Daily worklists by role`: для linked animal показывается текущий repro state

## Ограничения

- это не новый backend planner и не новая canonical event schema;
- state machine не ломает текущие `dm_repro_events` и mating plan flows;
- derived transitions полностью считаются в core и покрыты тестами.
