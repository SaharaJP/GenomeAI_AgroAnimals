# Observability 2.0

## Что централизовано

Введён единый пакет `src/core/observability`:

- `correlation.py` — contextvars-контекст для `request_id`, `run_id`, `data_version`, `config_version`, `user_id`, `job_id`.
- `logger.py` — JSON structured logs в едином формате `genomeai.observability.log.v1`.
- `metrics.py` — in-memory runtime metrics для web/API, jobs и CLI/pipeline команд.

Legacy-импорт `web_cabinet.observability` сохранён как shim на `core.observability`.

## Где интегрировано

- **Web/API**: middleware в `web_cabinet/app.py`
  - принимает `X-Request-ID` или генерирует новый;
  - прокидывает `request_id` в correlation context;
  - добавляет `X-Request-ID` в response headers;
  - считает request metrics и пишет structured events `http.request.started|finished|failed`.
- **Audit log**: `core.audit.write_audit(...)` теперь автоматически подхватывает `request_id`, `data_version`, `run_id` из correlation context, если они не переданы явно.
- **Job runner / worker**: `web_cabinet/worker.py`
  - создаёт job-level correlation context;
  - прокидывает correlation env (`GENOMEAI_REQUEST_ID`, `GENOMEAI_JOB_ID`, `GENOMEAI_RUN_ID`, `GENOMEAI_DATA_VERSION`, `GENOMEAI_USER_ID`, `GENOMEAI_TENANT_ID`) в subprocess CLI;
  - считает job metrics и пишет `job.started|finished|failed`.
- **CLI / pipelines**: `src/genomeai/cli.py`
  - строит correlation context из argv + env;
  - пишет `cli.command.started|finished|failed`;
  - считает command metrics.
- **Web frontend / Android / backend contour** — structured events проходят через backend API, web_cabinet internal surface и server deployment baseline.

## Формат structured log

Каждое событие — одна JSON-строка в stderr/stdout лог-потоке процесса:

- `schema`
- `ts`
- `level`
- `event`
- correlation fields: `request_id`, `run_id`, `data_version`, `config_version`, `user_id`, `job_id`
- adapter/component fields: `component`, `command`, `path`, `method`, `status_code`, `duration_sec`, и др.

## Metrics snapshot

`/api/observability` и `/metrics` возвращают snapshot из `core.observability.metrics.snapshot()`:

- `uptime_sec`
- `jobs` — backward-compatible агрегаты по kind
- `requests` — totals + per-route статистика
- `commands` — статистика CLI/pipeline команд

## Env knobs

Поддержаны безопасные дефолты:

- `GENOMEAI_STRUCTURED_LOGS=1|0` — включение structured logs
- `GENOMEAI_LOG_LEVEL=INFO|WARNING|ERROR|...`
- runtime correlation env для jobs/CLI:
  - `GENOMEAI_REQUEST_ID`
  - `GENOMEAI_JOB_ID`
  - `GENOMEAI_PUBLIC_JOB_ID`
  - `GENOMEAI_RUN_ID`
  - `GENOMEAI_DATA_VERSION`
  - `GENOMEAI_CONFIG_VERSION`
  - `GENOMEAI_USER_ID`
  - `GENOMEAI_TENANT_ID`

## Обратная совместимость

- существующие CLI команды, web routes и audit schema не менялись;
- существующий shape `jobs` в observability snapshot сохранён;
- `web_cabinet.observability` продолжает работать через shim.
