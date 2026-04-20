# PostgreSQL runtime cutover foundation (T34-01)

## Что сделано

На этом шаге **не объявляется завершённый cutover**. Вместо этого собрана безопасная база для staged migration:

- введён единый runtime storage contract для backend/web state;
- разделены профили:
  - `dev` / `test` — `sqlite` compat path;
  - `stage` / `prod` / `adult` — только `postgres` runtime intent;
- adult runtime получил fail-fast guards:
  - без `GENOMEAI_RUNTIME_POSTGRES_DSN` или `GENOMEAI_RUNTIME_POSTGRES_DSN_FILE` старт запрещён;
  - при попытке использовать legacy `web.db` в adult/stage/prod старт запрещён;
  - при выбранном `postgres` и отсутствии драйвера `psycopg` старт запрещён;
- readiness/observability публикуют active storage backend и migration status;
- добавлен baseline layout для Alembic (`alembic.ini`, `src/core/migrations/alembic/...`).

## Новые runtime env

- `GENOMEAI_RUNTIME_STORAGE_BACKEND` — `sqlite` или `postgres`.
- `GENOMEAI_RUNTIME_POSTGRES_DSN` — прямой DSN.
- `GENOMEAI_RUNTIME_POSTGRES_DSN_FILE` — файл с DSN для stage/prod/adult.

## Поведение профилей

### Dev / Test

Допускается SQLite compat path:

- `connect(web.db)` разрешён;
- startup seed/init_db разрешён;
- readiness возвращает backend=`sqlite`.

### Stage / Prod / Adult

Требуется Postgres runtime intent:

- backend должен быть `postgres`;
- DSN обязателен;
- `web.db` запрещён как runtime backend;
- отсутствие Postgres driver/migration baseline блокирует startup.

Это сделано специально, чтобы команда больше не могла случайно поднять «adult contour», который фактически всё ещё сидит на SQLite.

## Migration discipline baseline

Введён baseline для дисциплины миграций:

- `alembic.ini`
- `src/core/migrations/alembic/env.py`
- `src/core/migrations/alembic/script.py.mako`
- `src/core/migrations/alembic/versions/`

На T34-01 это **только layout и policy baseline**. Реальные Postgres revisions и runtime entity cutover выполняются следующими staged итерациями.

## Diagnostics / observability

Новые сигналы:

- `settings.runtime_storage_backend`
- `settings.runtime_storage_diagnostics`
- `/readyz` headers:
  - `X-GenomeAI-Storage-Backend`
  - `X-GenomeAI-Storage-Profile`
  - `X-GenomeAI-Storage-Migration-Status`
- `/api/observability.runtime_storage`
- `/api/runtime-storage`
- boundary readiness source paths теперь включают `runtime_storage`

## Что доказано этим шагом

- adult runtime больше нельзя честно поднять на legacy `web.db` path без явного fail-fast;
- backend storage теперь явно виден в runtime diagnostics;
- появилась опорная abstraction для staged cutover;
- migration discipline вынесена в отдельный baseline.

## Что ещё не доказано

- что runtime entities уже реально работают через PostgreSQL;
- что migrations реально накатываются на живой Postgres contour;
- что workers и scheduler уже используют Postgres runtime persistence вместо SQLite;
- что выполнен end-to-end runtime proof взрослого deployment contour.

## Следующие безопасные шаги

1. Ввести Postgres driver/runtime adapter для первой ограниченной группы runtime entities.
2. Поднять отдельный runtime schema version table для Postgres path.
3. Перенести queue/job tables с явным repo boundary и dual-read/dual-write policy только там, где это оправдано.
4. После каждого staged cutover прогонять live proof и обновлять evidence manifest.
