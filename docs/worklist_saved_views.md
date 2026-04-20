# Worklist saved views

## Что сделано в T21-05

В ежедневных operational worklist surfaces добавлена интеграция с существующим механизмом `saved views` и `favorites` без нового state store.

### Что поддержано
- персональные (`user`) и shared (`shared`) saved views для:
  - `daily_worklists_by_role`
  - `operational_planner`
- pinned filters как сохранённый page state:
  - день
  - include upcoming
  - поиск
  - лимит
  - selected worklist / selected planner item
  - planner role / owner / team / sources
- favorites для конкретного `worklist`
- deep-link/context restoration через metadata favorites и `apply_saved_view_state(...)`

### Принципы
- reuse существующего `saved_views_v1` и `favorites_v1`
- shared views доступны только при текущем RBAC (`configs.manage` для shared create)
- без client-only hacks: state хранится в server-side web DB и восстанавливается через whitelisted session keys

### Daily execution UX
Пользователь может:
1. настроить рабочий список на сегодня;
2. сохранить его как personal/shared view;
3. отметить конкретный worklist как favorite;
4. позже открыть тот же список и тот же selected worklist без потери контекста.

### Ограничения текущей итерации
- pinned filters остаются UI state, а не отдельной доменной сущностью;
- favorite открывает контекст через metadata/state, но не создаёт отдельный backend navigation registry;
- planner favorites не добавлялись отдельно: для planner используется saved view.
