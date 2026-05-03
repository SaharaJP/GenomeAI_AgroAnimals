# Audit retention and archive

## Что добавлено
- Facet-агрегации для Audit Log: action_group, status, top actions, top users.
- Scope-фильтр: `active`, `archived`, `all`.
- Retention policy из `configs/security/audit_retention_v1.yaml`.
- Ручная batch-архивация старых записей через `POST /api/audit/archive-old`.

## Конфиг
Файл: `configs/security/audit_retention_v1.yaml`

Поля:
- `enabled` — разрешена ли архивация.
- `archive_after_days` — возраст записи, после которого она считается кандидатом на архив.
- `max_archive_batch_size` — верхний лимит записей за один batch.
- `facets.top_actions_limit`, `facets.top_users_limit` — лимиты для агрегатов в UI/API.

## Поведение
- Архивация не удаляет события физически.
- В active-scope архивированные записи скрыты.
- Каждая batch-архивация фиксируется в `audit_archive_runs` и как audit-событие `config.audit_retention.apply`.
