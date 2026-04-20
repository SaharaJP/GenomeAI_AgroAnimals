# Daily worklists by role

## Что сделано в T21-02

- Добавлен единый role-aware экран `pages/43_Daily_Worklists_By_Role.py`.
- Экран использует только unified worklist core layer (`core.workflow.worklists`) и не считает тяжёлые агрегаты в Streamlit.
- Для ролей `Operator`, `Zootech`, `Vet`, `Director` показывается список `что делать сегодня` с полями:
  - `priority`
  - `due`
  - `confidence`
  - `expected_effect`
  - `linked facts`
  - linked object / alert / decision
- Добавлены быстрые действия:
  - `accept`
  - `postpone`
  - `complete`
  - `escalate`
  - `open object`
- На Home v3 добавлен lightweight preview-блок `Что делать сегодня`, который ведёт в полный daily worklist screen и не подменяет Home pages отдельным таск-трекером.

## Page pattern

Единый page pattern:
1. header + role-aware subtitle
2. summary metrics (`в фокусе`, `просрочено`, `на сегодня`, `высокий приоритет`)
3. table текущего списка
4. detail panel выбранного worklist
5. quick actions

## Источник данных

Используется `list_worklists_for_role_today(...)` из core.
UI only:
- запрашивает уже нормализованные worklists,
- отображает ready-made fields,
- вызывает use-cases для status changes.

## Status changes

Никаких status changes напрямую из UI нет.
Используются только use-cases:
- `accept_worklist_use_case(...)`
- `postpone_worklist_use_case(...)`
- `close_worklist_use_case(...)`
- `escalate_worklist_use_case(...)`

## RBAC

- Экран требует `tasks.view`.
- `accept` доступен при `tasks.write` или `tasks.close`.
- `postpone` и `escalate` требуют `tasks.write`.
- `complete` требует `tasks.close`.

## Acceptance intent

Пользователь должен понимать:
- что делать сегодня,
- почему именно это в приоритете,
- какое действие можно сделать за 1 клик,
- в какой linked object перейти для исполнения.
