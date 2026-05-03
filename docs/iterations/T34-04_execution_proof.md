# T34-04 execution proof — Redis broker queue cutover foundation

Status: **partially_proven**

## Scope actually executed
- Added Redis-backed queue runtime abstraction.
- Added dedicated worker execution mode.
- Added adult fail-fast guard forbidding embedded worker when queue backend is Redis.
- Added queue diagnostics endpoint and readiness headers.
- Added auto-enqueue from runtime job creation into broker runtime.
- Updated adult compose/env posture for Redis queue runtime.

## Commands executed

### Syntax / import validation
```bash
python -m py_compile \
  src/core/infra/queue_runtime.py \
  src/core/infra/web_db.py \
  web_cabinet/worker.py \
  src/web_cabinet/worker.py \
  web_cabinet/app.py \
  src/web_cabinet/app.py \
  web_cabinet/deploy_guard.py \
  src/web_cabinet/deploy_guard.py \
  scripts/service_worker.py
```

### Targeted T34-04 tests
```bash
pytest -q \
  tests/test_t34_04_queue_runtime_foundation.py \
  tests/test_t34_04_embedded_worker_guard.py \
  tests/web/test_t34_04_queue_observability.py
```
Result: **5 passed**

### Regression suite
```bash
pytest -q \
  tests/test_t16_02_web_lifespan.py \
  tests/test_t34_01_postgres_cutover_foundation.py \
  tests/test_t34_02_auth_storage_foundation.py \
  tests/test_t34_03_runtime_state_storage_foundation.py \
  tests/web/test_t34_01_runtime_storage_observability.py \
  tests/web/test_t34_02_auth_admin_diagnostics.py \
  tests/web/test_t34_03_runtime_state_observability.py \
  tests/web/test_nfr_controls.py
```
Result: **24 passed**

### Combined executed proof
```bash
pytest -q \
  tests/test_t34_04_queue_runtime_foundation.py \
  tests/test_t34_04_embedded_worker_guard.py \
  tests/web/test_t34_04_queue_observability.py \
  tests/test_t16_02_web_lifespan.py \
  tests/test_t34_01_postgres_cutover_foundation.py \
  tests/test_t34_02_auth_storage_foundation.py \
  tests/test_t34_03_runtime_state_storage_foundation.py \
  tests/web/test_t34_01_runtime_storage_observability.py \
  tests/web/test_t34_02_auth_admin_diagnostics.py \
  tests/web/test_t34_03_runtime_state_observability.py \
  tests/web/test_nfr_controls.py
```
Result: **29 passed**

## What this proves
- Adult contour can be guarded against embedded worker execution when Redis queue backend is selected.
- Job creation path can enqueue broker payloads with idempotency semantics.
- Dedicated worker path can be represented separately from embedded worker mode.
- Queue diagnostics are exposed through readiness/observability/API surfaces.
- T34-01/T34-02/T34-03 regression surface remains green on the executed suite.

## What this does not yet prove
- Live Redis consume/ack/fail on a real Redis service.
- Scheduler/API → Redis → dedicated worker → persistence end-to-end proof on adult-like runtime.
- Real stuck-job detection and dead-letter inspection against a live broker.
- That web/backend processes are no longer executing any background jobs in a real deployed adult contour.
