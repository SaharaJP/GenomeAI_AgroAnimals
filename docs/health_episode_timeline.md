# Health episode timeline

## Что добавлено
- `health episode` как first-class object в core/use-cases, без переписывания хранения `dm_health_events` и `treatment_journal_v1`.
- Единый snapshot `build_health_episode_snapshot(...)`, который собирает в эпизод:
  - health events,
  - treatments,
  - alerts,
  - worklists,
  - decisions,
  - outcomes.
- Новый экран `pages/53_Health_Episode_Timeline.py` с current state, timeline и переходами в profile / worklist / reports.
- Timeline теперь показывает не только clinical facts, но и operational chain: creation of worklist → decision → outcome.

## Linking rules
Linkage делается прозрачно и детерминированно:
1. Базовый ключ эпизода = `animal + family`.
2. `family` нормализуется по `event_type / condition_code / notes / treatment_type / diagnosis_label`.
3. Новое событие попадает в существующий эпизод, если gap между anchor dates не превышает `max_gap_days_same_family`.
4. `treatments` линкуются по `linked_health_event_id` или через окно around episode.
5. `alerts` линкуются по `animal + family keywords + time window`.
6. `worklists` линкуются по `animal + health/vet type` или через related alert.
7. `decisions` линкуются по `animal + related alert` или через time window.
8. `outcomes` линкуются по `worklist_id` или `object animal + time window`.

Все правила versioned в `configs/health/health_episode_rules.yaml`.

## Current state
State эпизода считается в core:
- `active` — есть active treatment или событие ещё в acute active window.
- `blocked` — есть открытый alert по эпизоду.
- `monitoring` — есть открытый follow-up/worklist или эпизод ещё требует наблюдения.
- `resolved` — есть formal outcome (`done/cancelled/no_effect`) и нет активного treatment/alert.

## Ограничения
- Нет retrospective clustering на неявных ML-эвристиках.
- Это не disease model и не diagnosis engine.
- `health episode` сейчас derived object; source of truth для первичных фактов остаются existing health/treatment/alert/workflow stores.
