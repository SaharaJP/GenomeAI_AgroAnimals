# T34-03 execution proof

Дата: 2026-04-14

## Scope
Фактическое выполнение и проверка deliverables T34-03:
- Postgres migration of jobs/workflow/admin runtime state
- runtime-state diagnostics
- support bundle posture update
- migration verification tooling baseline

## Executed checks

### 1. Targeted regression suite
Команда:

```bash
pytest -q \
  tests/test_t34_03_runtime_state_storage_foundation.py \
  tests/web/test_t34_03_runtime_state_observability.py \
  tests/test_t34_03_support_bundle_runtime_state.py \
  tests/test_t34_02_auth_storage_foundation.py \
  tests/web/test_t34_02_auth_admin_diagnostics.py \
  tests/test_t34_01_postgres_cutover_foundation.py \
  tests/web/test_t34_01_runtime_storage_observability.py \
  tests/web/test_t32_03_auth_boundary.py \
  tests/web/test_nfr_controls.py \
  tests/test_t17_04_artifact_lifecycle.py
```

Результат:
- 29 passed
- 26 warnings

### 2. What this proves
Подтверждено:
- runtime-state abstraction присутствует и импортируется;
- `/api/runtime-state` и `/api/observability` публикуют runtime-state snapshot;
- `/readyz` публикует runtime-state headers;
- support bundle при postgres posture включает `diagnostics/runtime_state_summary.json`;
- support bundle при postgres posture не включает `diagnostics/web_db_summary.json` как default path;
- T34-01 / T34-02 regression path не сломан;
- artifact lifecycle / auth boundary / базовые NFR не сломаны.

## Deliverables present in repo
- `src/core/infra/runtime_state_storage.py`
- `src/core/migrations/alembic/versions/20260414_03_runtime_state_postgres_baseline.py`
- `scripts/runtime_state_backfill_postgres.py`
- `scripts/runtime_state_verify_postgres_cutover.py`
- `deploy/adult/ops/diagnostic_sql/runtime_state_checks.sql`
- `docs/postgres_runtime_state_cutover.md`

## Honest status
### proven
- diagnostics/supportability baseline for migrated runtime state
- support bundle posture update for postgres runtime state
- T34-03 code surfaces load and pass targeted regression

### partially_proven
- schema baseline and verification tooling exist for jobs/workflow/admin runtime entities
- runtime-state observability is exposed and tested

### not_proven
- live postgres read/write proof for all migrated entities
- end-to-end worker/jobs/workflow/admin execution on adult postgres contour
- completed old->new backfill with verified entity parity on a real postgres environment

## Go / no-go for full claim
Честный итог для полного claim "critical adult runtime state lives in Postgres":
- current status: `partially_proven`
- full `proven` still requires live postgres runtime proof
