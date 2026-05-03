# Completion / outcome loop

## Что сделано в T21-04
- Добавлена append-only модель `completion_outcomes_v1` для формального итога выполнения worklist/task.
- Формализованы outcome statuses: `done`, `cancelled`, `deferred`, `no_effect`, `escalated`.
- Добавлены advisory reason codes в `configs/workflow_v2/reason_codes.yaml` (`completion_outcome`).
- Реализован use-case `record_completion_outcome_use_case(...)` для записи outcome без скрытых update-path вне core.
- `close_worklist_use_case(...)` теперь пишет formal outcome и сохраняет совместимость текущего completion flow.
- Добавлено безопасное auto-link поведение:
  - для `done` alert резолвится только если outcome финальный и уже есть decision linkage;
  - для `deferred/escalated` при необходимости создаётся append-only decision `worklist.outcome`.
- В `tasks_v1` добавлены summary-поля latest outcome (`latest_outcome_*`, `outcome_metrics_json`) для быстрого чтения без heavy recompute.
- Добавлен агрегатор `aggregate_execution_quality_metrics(...)` для аналитики execution quality.

## Состав deliverables
- `src/core/workflow/outcomes.py`
- `src/core/workflow/worklists.py` (close → outcome integration)
- `src/core/workflow/tasks.py` (patch support for latest outcome fields)
- `src/core/workflow/policies.py`
- `src/core/domain/enums.py`
- `src/core/domain/records.py`
- `src/core/domain/adapters.py`
- `src/core/infra/repositories.py`
- `src/core/infra/web_db.py`
- `src/core/migrations/registry.py`
- `configs/workflow_v2/reason_codes.yaml`

Statuses: done / cancelled / deferred / no_effect / escalated

## Модель outcome
`completion_outcomes_v1` хранит append-only outcome record с linkage на:
- `worklist_id` / `task_id`
- `linked_decision_id`
- `related_alert`
- `object_type` / `object_id`
- owner/team/type/priority/confidence snapshot
- `outcome_status`, `reason_code`, `comment`
- metrics/auto-actions JSON

## Семантика статусов
- `done` — действие выполнено, итог позитивный/завершённый.
- `cancelled` — выполнение отменено.
- `deferred` — действие перенесено, task/worklist остаётся открытой.
- `no_effect` — действие выполнено, но ожидаемый эффект не подтверждён; task формально закрывается, alert автоматически не резолвится.
- `escalated` — действие передано выше/другой роли, task/worklist остаётся открытой в review-stage.

## Execution quality metrics
Агрегатор `aggregate_execution_quality_metrics(...)` считает:
- `by_outcome_status`
- `by_reason_code`
- `on_time_rate`
- `auto_alert_resolution_rate`
- `decision_link_rate`
- `mean/median created_to_outcome_hours`
- `bottlenecks` по командам

## Ограничения
- Это не новый календарный backend и не новая параллельная task-модель.
- Outcome reasons остаются advisory-code моделью: свободный текст по-прежнему допустим, если он не пустой.
- Для `deferred/escalated` автоматически создаётся decision linkage только при безопасных условиях и только в append-only Decision Log.
