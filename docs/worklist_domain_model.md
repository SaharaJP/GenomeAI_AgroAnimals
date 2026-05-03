# T21-01 — unified worklist domain model

## Что зафиксировано

`worklist` введён как first-class operational object, но **без отдельной параллельной task/worklist БД-модели**.

Источник истины для хранения — существующая таблица `tasks_v1`, расширенная worklist-полями:
- `worklist_type`
- `confidence`
- `linked_decision_id`
- `linked_task_id`
- `linked_source_facts_json`

Идентификатор worklist = `task_id`.

## Типы worklist

Поддерживаются типы:
- `reproduction`
- `vet`
- `health_follow_up`
- `milk_quality`
- `movement`
- `culling_review`
- `data_cleanup`
- `manager_review`

## Обязательная связность

Worklist хранит и/или вычисляет связи:
- linked object: `object_type` + `object_id`
- linked alert: `related_alert`
- linked decision: `linked_decision_id`
- linked task: `linked_task_id`
- linked source facts: `linked_source_facts_json`

Для чтения use-case возвращает `signal_chain`:
- `signal`
- `triage`
- `decision`
- `task`
- `outcome`

Это даёт явную трассировку `signal → triage → decision → task → outcome`.

## Lifecycle

Статусы остаются совместимыми с `tasks_v1`:
- `open`
- `in_progress`
- `done`
- `cancelled`

Дополнительный operational lifecycle идёт через `stage`:
- `triage`
- `plan`
- `execute`
- `review`
- terminal: `done` / `cancelled`

Изменение статусов и lifecycle допускается **только через use-cases**:
- `create_worklist_use_case(...)`
- `triage_worklist_use_case(...)`
- `start_worklist_use_case(...)`
- `link_worklist_decision_use_case(...)`
- `close_worklist_use_case(...)`

## Audit

Worklist use-cases пишут canonical audit events:
- `worklist.create`
- `worklist.triage`
- `worklist.start`
- `worklist.link_decision`
- `worklist.close`

`object_type='worklist'`, `object_id=<task_id/worklist_id>`.

## Совместимость

- существующие `tasks/alerts/decisions` не удаляются и не переименовываются;
- старые task-rows читаются как worklist best-effort: `worklist_type` выводится из `task_type/domain/related_alert`, если колонка ещё пустая;
- закрытие worklist использует текущий `close_task(...)`, поэтому decision log и optional alert resolution остаются совместимыми.
