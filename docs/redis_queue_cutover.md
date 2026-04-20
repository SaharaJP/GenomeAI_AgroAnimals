# T34-04 — Redis broker queue cutover + dedicated worker/scheduler execution model

Статус этого шага: **partially_proven**.

Этот инкремент **не объявляет live Redis cutover полностью доказанным**, но переводит кодовую базу на честный staged-path:
- producer path может публиковать background jobs в Redis-backed broker runtime;
- dedicated worker может забирать job из Redis queue и исполнять её отдельно от web/backend process;
- embedded worker в adult contour запрещён fail-fast guard'ом;
- появились dead-letter / retry counters / stuck-job visibility / queue diagnostics.

## Что изменено

### 1. Queue runtime abstraction
Добавлен `src/core/infra/queue_runtime.py`:
- `QueueRuntimeSettings`
- `QueueRuntimeDiagnostics`
- `QueueEnvelope`
- `RedisWireClient` (минимальный RESP-клиент без внешнего python-пакета)
- `RedisQueueBroker`
- `SqliteCompatQueueBroker`
- `build_queue_runtime_summary_payload()`

### 2. Producer path
`create_job()` и `create_retry_job()` в `src/core/infra/web_db.py` теперь:
- создают runtime job row как раньше;
- при `GENOMEAI_JOB_QUEUE_BACKEND=redis` публикуют envelope в broker;
- используют idempotency key на `public_job_id`, чтобы не дублировать enqueue одной и той же job.

Это покрывает:
- API enqueue path
- scheduler enqueue path
- connector enqueue path
- retry enqueue path

### 3. Dedicated worker execution path
`web_cabinet/worker.py` и `src/web_cabinet/worker.py` теперь поддерживают два режима:
- `execution_model="embedded"` — compat/dev/test
- `execution_model="dedicated"` — adult Redis worker service

Для adult Redis contour:
- embedded worker **запрещён**;
- dedicated worker claim'ит job из Redis queue;
- после claim worker читает runtime job row, исполняет job и делает ack/fail.

### 4. Retry / dead-letter / stuck diagnostics
Redis queue runtime хранит:
- `pending`
- `processing`
- `deadletter`
- `inflight`
- stats hash (`enqueued_total`, `claimed_total`, `acked_total`, `failed_total`, `retried_total`)

Stuck jobs определяются по `heartbeat_at` и `visibility_timeout_sec`.

### 5. Fail-fast adult guards
`deploy_guard.validate_runtime_config()` теперь требует:
- `GENOMEAI_JOB_QUEUE_BACKEND=redis` для adult contour;
- `GENOMEAI_WEB_DISABLE_WORKER=1` для adult Redis contour.

Это исключает backend/web process как executor supposedly background jobs.

### 6. Queue observability
Добавлены:
- `GET /api/queue-runtime`
- расширение `/api/observability` полем `queue_runtime`
- readiness headers:
  - `X-GenomeAI-Queue-Backend`
  - `X-GenomeAI-Queue-Broker-Status`

## Новые env / deploy настройки
Добавлены переменные:
- `GENOMEAI_JOB_QUEUE_BACKEND`
- `GENOMEAI_REDIS_DSN`
- `GENOMEAI_QUEUE_KEY_PREFIX`
- `GENOMEAI_QUEUE_VISIBILITY_TIMEOUT_SEC`
- `GENOMEAI_QUEUE_IDEMPOTENCY_TTL_SEC`
- `GENOMEAI_QUEUE_CLAIM_BLOCK_TIMEOUT_SEC`

В `deploy/adult/compose.yaml` adult python-services теперь получают:
- `GENOMEAI_JOB_QUEUE_BACKEND=redis`
- `GENOMEAI_REDIS_DSN=redis://redis:6379/0`

## Что считается sync и не переводится в broker на этом шаге
На этом шаге не нужно искусственно ставить в очередь:
- очень короткие локальные чтения diagnostics/readiness;
- чтение dashboard/report metadata;
- admin/read-only endpoints.

В очередь идут long-running / background execution flows:
- pipeline jobs
- connector runs
- retry jobs
- scheduler-produced jobs

## Что ещё не доказано
Чтобы закрыть T34-04 до `proven`, нужен отдельный live proof:
- реальный Redis service в adult-like контуре;
- worker consume/ack/fail against live Redis;
- scheduler enqueue → Redis → worker → result persistence;
- dead-letter / stuck detection на живом окружении;
- operator diagnostics на живом runtime.

## Минимальные проверки этого шага
- unit tests queue runtime / auto-enqueue / adult embedded worker guard;
- web test на `/api/queue-runtime` и readiness headers;
- py_compile на изменённые файлы.
