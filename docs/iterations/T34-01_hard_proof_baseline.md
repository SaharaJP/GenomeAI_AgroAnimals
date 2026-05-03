# T34-01 — hard-proof baseline audit

## Scope

Baseline evidence audit for five T34 claims: PostgreSQL runtime persistence, Redis/queue workers, unified server auth/session/RBAC, adult deployment runtime proof, and operational supportability.

## Result summary

| Question | Status | Why |
|---|---|---|
| PostgreSQL runtime persistence | `not_proven` | Compose contains PostgreSQL, but executable runtime still points to sqlite/web.db and no live Postgres persistence path is demonstrated. |
| Redis/queue + dedicated workers | `not_proven` | Compose contains Redis/worker/scheduler, but job execution remains sqlite-backed in-process worker logic. |
| Unified server auth/session/RBAC for web + Android + backend | `partially_proven` | Unified auth contract and passing boundary tests exist, but legacy fallback remains in the live request path. |
| Adult deployment contour live end-to-end runtime proof | `not_proven` | Deployment artifacts and validation scripts exist, but no live contour proof artifact was captured. |
| Operational supportability | `partially_proven` | Runbooks/support bundle/backup-restore tests exist, but proof is local/sqlite-oriented rather than adult runtime contour proof. |

## Evidence highlights

### 1. PostgreSQL
- `deploy/adult/compose.yaml` declares a `postgres` service and makes backend depend on it.
- `src/core/infra/database.py` only provides backend selection/placeholder formatting for `postgres`; it does **not** provide a working repository layer or runtime connection path.
- `src/web_cabinet/app.py` and related modules still initialize/check `web.db` and rely on sqlite-backed `core.infra.web_db`.
- `src/genomeai/backup_restore.py` still opens sqlite directly.

### 2. Redis / queue
- `deploy/adult/compose.yaml` declares `redis`, `worker`, `scheduler`.
- `web_cabinet/worker.py` explicitly says: jobs are stored in sqlite and a single thread picks queued jobs.
- `src/core/application/job_runner.py` enqueues jobs through `create_job(...)` in web DB storage.
- Repository search did not find an active Redis queue execution path (`redis` client / `rq` / `celery` / `dramatiq` / `arq`).

### 3. Unified auth/session/RBAC
- `docs/auth_rbac_for_web_and_mobile.md` defines a single `auth_sessions_v1` model for web and Android with server-side RBAC.
- `src/web_cabinet/auth_boundary_v1.py` implements login/refresh/me/logout/sessions endpoints.
- `tests/web/test_t32_03_auth_boundary.py` passed and gives positive evidence that bearer/refresh/revoke flows work in the repository test harness.
- But `src/web_cabinet/auth.py` still contains `legacy fallback` and `legacy_cookie_session` execution path.

### 4. Adult deployment proof
- `deploy/adult/compose.yaml`, `docs/deployment_full_guide.md`, `docs/operations_runbook.md`, and deployment validation tests exist.
- `scripts/validate_t32_10_server_deployment.py` checks file/service presence only; it does not prove a live contour.
- No recorded proof pack was found for: compose up → healthy services → login → enqueue → worker execution → artifact persistence/download on adult contour.

### 5. Operational supportability
- Supportability artifacts exist: backup/restore docs, support bundle script, operations runbook, CI gates docs.
- Executed tests passed for backup/restore drill and support bundle lifecycle.
- However, these proofs are not yet tied to PostgreSQL + Redis + object storage adult contour.

## Executed checks

1. `pytest -q tests/test_t32_10_server_deployment_baseline.py tests/test_t32_10a_production_security_baseline.py tests/test_t32_13_deployment_full_guide.py tests/test_t13_06_backup_restore_step1.py tests/test_t13_06_backup_restore_step2.py tests/test_t17_04_artifact_lifecycle.py tests/test_t32_03_auth_contract_models.py tests/web/test_t32_03_auth_boundary.py`
   - Result: `28 passed, 26 warnings`
2. `pytest -q tests/test_t17_07_backup_restore_drill.py tests/web/test_nfr_controls.py`
   - Result: `9 passed, 28 warnings`

## Go / no-go

`no_go`

Reason: the repository now proves baseline documentation/tests and a partially unified auth contract, but it does **not** yet prove the three critical runtime claims required for honest T34 messaging:
1. PostgreSQL is the actual runtime persistence layer,
2. Redis is the actual queue backbone for background jobs,
3. adult deployment contour has passed a live end-to-end runtime proof.

## Recommended next increment

T34-02 should focus only on **runtime persistence proof**:
1. isolate every sqlite runtime path still used in adult/prod,
2. classify each as keep/replace/remove,
3. implement a single PostgreSQL-backed metadata store path for users/sessions/jobs/audit,
4. add a hard CI gate failing when adult/prod still points to sqlite,
5. produce a reproducible proof pack for that question alone.
