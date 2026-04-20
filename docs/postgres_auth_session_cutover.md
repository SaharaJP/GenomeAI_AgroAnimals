# T34-02 — PostgreSQL migration of auth/session/RBAC state + audit consistency

## Что сделано в этой итерации

Это **staged cutover increment**, а не финальный complete cutover.

В репозитории введена отдельная runtime-auth abstraction поверх T34-01 storage foundation:

- `src/core/infra/runtime_auth_storage.py`
- `SqliteCompatAuthStorage` для `dev/test`
- `PostgresAuthStorage` для `adult/stage/prod`
- явная диагностика auth storage backend
- явный запрет legacy cookie-only fallback в adult postgres profile

Также добавлены базовые auth/session diagnostics и traceability:

- active sessions
- session revoke status
- refresh lineage
- failed auth attempts
- storage backend visibility

## Что именно теперь покрывает runtime auth storage

На этом шаге abstraction/wiring покрывают:

- user lookup
- role permission resolution
- session create / get / touch
- access/refresh token lookup
- token rotate
- session revoke / revoke-all
- session listing
- refresh lineage listing
- failed auth attempt logging/listing

## SQLite compat vs adult Postgres

### Dev/Test

`sqlite` compat path по-прежнему разрешён только для локальной совместимости и тестов.

### Adult/Stage/Prod

- auth runtime должен идти через `postgres`
- legacy cookie-only fallback запрещён
- попытка опереться на старую cookie-only сессию без runtime auth session должна завершаться `401 auth.legacy_cookie_session_forbidden`

Это убирает скрытый обход server-side auth/session модели в adult contour.

## Session diagnostics/admin tools

Добавлены admin-safe endpoints:

- `GET /api/app/v1/auth/admin/runtime-storage`
- `GET /api/app/v1/auth/admin/sessions`
- `GET /api/app/v1/auth/admin/sessions/{session_id}`
- `GET /api/app/v1/auth/admin/failed-attempts`

Что видно:

- active backend
- active sessions
- revoke status
- refresh lineage
- failed auth reason visibility
- scope snapshot в session model

## Audit consistency

Привилегированные auth/admin actions продолжают audit-log'ироваться через существующий audit path.

Для session diagnostics добавлена отдельная append-oriented traceability в runtime auth state:

- `auth_session_refresh_lineage_v1`
- `auth_failed_attempts_v1`

Это не заменяет общий audit log, а дополняет его операционными auth/session evidence.

## Migration / backfill baseline

Добавлен baseline Alembic revision:

- `src/core/migrations/alembic/versions/20260414_02_auth_runtime_postgres_baseline.py`

И explicit tool baseline:

- `scripts/auth_backfill_postgres.py`
- `scripts/auth_verify_postgres_cutover.py`

На этом шаге это именно **explicit baseline**, а не доказанный production backfill run.

## Ограничения / честный статус

Что доказано:

- auth/session wiring больше не обязано опираться на sqlite-only functions
- adult profile больше не должен использовать legacy cookie-only fallback
- refresh lineage и failed auth diagnostics есть и тестируются на compat path
- admin session diagnostics появились и проверяемы

Что пока не доказано:

- живой Postgres runtime run в этом контейнере
- фактический backfill данных users/roles/sessions из legacy sqlite в Postgres
- end-to-end revoke/refresh proof на реальном Postgres server

Итоговый статус шага: **partially_proven**.
