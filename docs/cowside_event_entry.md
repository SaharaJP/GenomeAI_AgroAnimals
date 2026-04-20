# Cowside event entry (T25-03)

Что сделано:
- mobile-first / cowside страница `pages/59_Cowside_Event_Entry.py`;
- поиск и выбор животного через общий core list surface, а не через отдельную mobile business logic ветку;
- bounded quick templates с фиксированными `event_type` + `reason_code`;
- быстрый submit события через `create_cowside_event_entry_use_case(...)`;
- optional follow-up creation через existing `create_worklist_use_case(...)`;
- recent append-only history по выбранному животному.

Ключевые use-cases:
- `list_cowside_event_templates(role=...)`
- `search_cowside_animals(input_dir=..., asof_date=..., role=..., q=...)`
- `create_cowside_event_entry_use_case(...)`

Принципы:
- нет отдельной mobile-only бизнес-логики по событиям;
- нет raw/freeform event semantics вне taxonomy;
- нет client-side state transition без server-side use-case;
- follow-up создаётся только через общий workflow layer.

Что хранится:
- append-only `animal_event` с `entry_mode='cowside_entry'`, `template_key`, `template_label` и `source_versions` в payload;
- optional linked worklist с `why.source='cowside_event_entry'`, `event_id`, `template_key` и `linked_source_facts`;
- audit trail:
  - `animal_event.quick_entry.create` (из общего quick entry use-case)
  - `worklist.create` (если follow-up создан)
  - `animal_event.cowside_entry.submit` (bridge-level audit)

Ключевые quick templates:
- `heat_observed`
- `insemination_done`
- `preg_check_positive`
- `preg_check_open`
- `treatment_started`
- `pen_move`
- `dry_off`
- `manual_note`

Acceptance focus:
- полевой пользователь может найти животное, выбрать bounded template, добавить комментарий и при необходимости сразу создать follow-up без перехода в desktop-heavy flow.
