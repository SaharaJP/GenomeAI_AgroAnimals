# Server runtime target

## Цель

Зафиксировать production-ready серверный контур, к которому должна идти система.

## Обязательные компоненты

### 1. API service

Основной синхронный слой:

- REST/HTTP API;
- auth;
- RBAC;
- CRUD/commands/queries;
- audit hooks;
- health/ready/version endpoints.

### 2. Worker service

Фоновые задачи:

- ingestion;
- QC;
- training;
- scoring;
- report generation;
- pack/export;
- heavy reconciliation jobs.

### 3. Scheduler service

Периодические задачи:

- регулярные data refresh jobs;
- SLA freshness checks;
- alert recomputation;
- backup checks;
- retention jobs;
- scheduled reports.

### 4. Relational database

Должна хранить:

- users/roles/sessions;
- workflow/task/decision state;
- audit metadata;
- job metadata;
- integration configs and statuses;
- publication/version registry metadata.

### 5. Object storage

Должно хранить:

- raw snapshots;
- QC reports;
- model artifacts;
- scoring outputs;
- fact packs;
- generated reports;
- export packages;
- attachment evidence.

### 6. Observability

Обязательно:

- structured logs;
- metrics;
- request/job correlation IDs;
- dashboards on errors/latency/freshness;
- alerting for failed jobs and degraded dependencies.

### 7. Backup / restore

Нужны:

- documented backup policy;
- restore drill;
- RPO/RTO expectations;
- artifact retention policy;
- rollback-compatible release path.

## Non-goals текущей итерации

Сейчас этот документ не выбирает окончательно конкретный стек очередей/БД/объектного хранилища. Он фиксирует обязательные runtime-capabilities, чтобы следующие итерации не скатывались обратно в локальный all-in-one запуск как единственную модель эксплуатации.
