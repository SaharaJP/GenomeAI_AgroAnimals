# T34-03 — PostgreSQL migration of jobs/workflow/admin runtime state

Статус этого шага: **partially_proven**.

Это не финальный cutover взрослого runtime contour, а staged migration step для остального критичного web/backend runtime state после T34-01/T34-02.

## Что сделано

### 1. Введён runtime state storage baseline
Добавлен отдельный runtime-state слой:

- `src/core/infra/runtime_state_storage.py`

Он публикует единый diagnostics snapshot по сущностям runtime state:

- `jobs`
- `audit_log`
- `alerts_v2`
- `tasks_v1`
- `decision_log_v2`
- `connector_runs`
- `saved_views_v1`
- `favorites_v1`
- `report_templates_v1`
- `report_approvals_v1`
- `whatif_scenarios_v1`
- `whatif_reports_v1`

Для `sqlite compat` слой показывает фактические counts и явно помечает legacy sqlite как primary state.
Для `postgres adult` слой публикует target posture и пытается читать live counts при доступном подключении.

### 2. Добавлен PostgreSQL migration baseline
Добавлена Alembic migration:

- `src/core/migrations/alembic/versions/20260414_03_runtime_state_postgres_baseline.py`

Она создаёт PostgreSQL baseline schema для критичного runtime state и индексы на support/admin-friendly paths:

- status/created_at
- tenant/object lineage
- due_at / linked_decision_id
- connector run history
- approvals / scenario / report metadata

### 3. Добавлены verification/backfill baseline scripts
Добавлены явные инструменты:

- `scripts/runtime_state_backfill_postgres.py`
- `scripts/runtime_state_verify_postgres_cutover.py`

Они пока работают как explicit staged tools:
- собирают legacy sqlite counts,
- публикуют runtime-state diagnostics,
- не делают hidden fallback,
- требуют `GENOMEAI_RUNTIME_STORAGE_BACKEND=postgres` для postgres backfill posture.

### 4. Обновлены observability / support diagnostics
Добавлены runtime-state diagnostics в:

- `/api/observability`
- `/api/runtime-state`
- readiness headers (`X-GenomeAI-Runtime-State-*`)
- API boundary readiness payload

### 5. Обновлён support bundle posture
Support bundle теперь:
- всегда включает `diagnostics/runtime_state_summary.json`
- включает `diagnostics/web_db_summary.json` только для sqlite compat path
- не тащит `web.db` как default primary runtime-state source при postgres backend

### 6. Добавлены maintenance-oriented artifacts
Добавлен SQL-файл для adult ops:

- `deploy/adult/ops/diagnostic_sql/runtime_state_checks.sql`

В нём есть:
- entity counts
- linkage sanity checks
- operational status checks
- retention-oriented admin queries

## Что это доказывает

Доказано:
- есть явный target list migrated runtime entities;
- есть PostgreSQL schema baseline для этих сущностей;
- support/admin diagnostics перестали считать `web.db` единственным default runtime-state источником;
- есть явный staged migration/verification path.

## Что это не доказывает

Пока **не доказано**:
- что все перечисленные runtime entities уже живут в PostgreSQL в живом adult contour;
- что worker / jobs / workflow endpoints реально читают и пишут migrated entities в live Postgres;
- что backfill old→new уже выполнен и сверка old vs new завершена без расхождений;
- что support/restore целиком работают на live Postgres runtime state.

## Что нужно для следующего шага

Чтобы поднять статус до `proven`, нужен live runtime proof:

1. adult-like PostgreSQL environment;
2. установленный Postgres driver;
3. выполнение old→new backfill;
4. entity counts verification;
5. runtime write/read verification для jobs/workflow/admin surfaces;
6. support bundle / restore / admin diagnostics proof уже против live Postgres runtime state.
