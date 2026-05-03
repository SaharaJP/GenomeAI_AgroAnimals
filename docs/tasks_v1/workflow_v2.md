# Workflow 2.0 (T12-01): задачи, SLA, назначение, метрики

## Модель `tasks_v1`

`tasks_v1` расширяется **аддитивно** (онлайн-миграция в `web_cabinet/db.py`).

Обязательные поля (базовые):
- `task_id`, `tenant_id`, `created_at`, `updated_at`
- `task_type`, `title`
- `status`: `open | in_progress | done | cancelled`
- `priority`: 1..5 (1 — высокий)

Поля Workflow 2.0:
- `domain`: `health | repro | data | qc | econ`
- `sla_hours`: число часов (если `due_at` не задан)
- `sla_source`: `cfg.default | user.due_at | derived.from_due_at`
- `assignee_team`: строка (команда)
- `assigned_at`: когда задача была назначена
- `stage`: этап/колонка канбан-доски (ad-hoc), значения из `configs/workflow_v2/stages.yaml`

Конфиги Workflow 2.0:
- `configs/workflow_v2/stages.yaml` — этапы (канбан)
- `configs/workflow_v2/teams.yaml` — справочник команд (если список непустой — включается валидация)

## SLA (по умолчанию)

Если задача создаётся **без** `due_at`, дедлайн вычисляется из `configs/workflow_v2/sla.yaml` по `(domain, priority)`.

Если `due_at` задан явно, то:
- `sla_hours` может быть выведен из `due_at - now` (best-effort)

## API (Web Cabinet)

- `GET /api/tasks_v1` — список + фильтры (`domain`, `assignee_team`, `overdue_only`)
- `GET /api/tasks_v1` — также поддерживает фильтр `stage`
- `POST /api/tasks_v1` — создание
- `POST /api/tasks_v1/{task_id}/take` — взять в работу (ставит `in_progress`, `started_at`)
- `POST /api/tasks_v1/{task_id}/assign` — назначить исполнителя/команду
- `POST /api/tasks_v1/{task_id}/update` — обновить редактируемые поля (без закрытия)
  - допускается `status: open|in_progress`
  - закрытие строго через `/close`
- `POST /api/tasks_v1/{task_id}/close` — закрыть (done/cancelled) + Decision Log
- `GET /api/tasks_v1/metrics` — метрики исполнения (lead time, overdue rate)
- `GET /api/tasks_v1/overdue` — топ просроченных активных задач (director quick view)
- `GET /api/tasks_v1/export` — экспорт CSV по текущим фильтрам (аудитируется как `tasks_v1.export`)

Справочники Workflow 2.0:
- `GET /api/workflow_v2/teams` — команды
- `GET /api/workflow_v2/stages` — этапы (канбан)

Все критичные действия пишутся в `audit_log`.

## Экспорт

В UI Worklist доступна кнопка **«Скачать CSV»** (экспорт текущей выборки с учётом лимита). Это действие логируется в `audit_log` как `tasks_v1.export`.

Для интеграций/BI можно использовать API: `GET /api/tasks_v1/export` (также пишет `audit_log`).

Дополнительно (назначение по username):
- `GET /api/users_v2` — список активных пользователей (для dropdown), доступно при `tasks.write`
- `GET /api/tasks_v1?owner_username=<username>` — фильтр по исполнителю
- `POST /api/tasks_v1/{task_id}/assign` — поддерживает `assignee_username` (вместо `owner_user_id`)
- `POST /api/tasks_v1/{task_id}/update` — поддерживает `assignee_username` (будет преобразован в `owner_user_id`)

## Метрики (Director)

Endpoint: `GET /api/tasks_v1/metrics?window_days=N`

Ответ (ключевые поля):
- `active_total`, `active_overdue`, `overdue_rate_active`
- `closed_window_total`, `lead_time_mean_h`, `lead_time_percentiles_h`
- `sla_adherence`:
  - `closed_with_due_window`
  - `closed_on_time_window`
  - `closed_late_window`
  - `on_time_rate_closed_window`
- breakdowns:
  - `by_domain[]` (дополнительно: SLA поля `sla_*_closed_window`)
  - `by_team[]`
  - `by_stage[]`
  - `by_priority[]`

Все расчёты выполняются в offline-core: `src/genomeai/workflow_v2/metrics.py`.
