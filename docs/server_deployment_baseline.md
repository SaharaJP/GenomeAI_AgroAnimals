# T32-10 — Server deployment baseline (adult production contour)

## Что фиксирует этот шаг

Этот шаг вводит **production-oriented multi-service deployment baseline** для GenomeAI AgroAnimals:

- reverse proxy / ingress;
- web frontend (`web_app`);
- backend API;
- worker;
- scheduler;
- PostgreSQL;
- Redis;
- artifact storage (MinIO/S3-compatible);
- observability / structured logs / metrics scrape baseline;
- backup / restore host-level procedures;
- environment profiles: `dev`, `test`, `stage`, `prod`.

Шаг **не обещает SLA** и **не утверждает**, что вся внутренняя persistence-модель уже мигрировала на PostgreSQL/Redis. Текущий backend по-прежнему работает в **compatibility mode** с существующей runtime-state моделью, но разворачивается уже как взрослый многосервисный контур.

## Целевая топология

В каталоге `deploy/adult/` зафиксирован новый deployment contour:

- `reverse-proxy` — Nginx ingress / reverse proxy;
- `web-frontend` — отдельный Next.js frontend;
- `backend-api` — FastAPI / canonical API boundary;
- `worker` — отдельный процесс job execution;
- `scheduler` — отдельный процесс periodic scheduling;
- `postgres` — dedicated relational DB baseline;
- `redis` — dedicated cache / future queue / coordination baseline;
- `artifact-storage` — MinIO как S3-compatible object storage baseline;
- `prometheus` — metrics scraping baseline.

## Что считается production discipline на этом шаге

1. **Нет target-state single-process контура**.
2. **API, worker и scheduler разведены по процессам**.
3. **Web frontend вынесен в отдельный сервис**.
4. **Ingress / reverse proxy обязателен**.
5. **Secrets/config не хардкодятся только в коде** — используются env/env-file и `*_FILE` path pattern.
6. **Health/readiness** есть у ingress, frontend, API, worker, scheduler, postgres, redis, minio, prometheus.
7. **Structured logs** идут в stdout/stderr сервисов; Nginx access log переведён в JSON format.
8. **Metrics baseline** даётся через `/metrics/prometheus` backend API + Prometheus scrape.
9. **Backup/restore** описаны как host-driven управляемые процедуры, а не как ad-hoc ручной copy/paste.

## Environment profiles

Используются:

- `deploy/adult/compose.yaml` — base contour;
- `deploy/adult/compose.dev.yaml`;
- `deploy/adult/compose.test.yaml`;
- `deploy/adult/compose.stage.yaml`;
- `deploy/adult/compose.prod.yaml`.

Примеры env:

- `deploy/adult/env/dev.env.example`
- `deploy/adult/env/test.env.example`
- `deploy/adult/env/stage.env.example`
- `deploy/adult/env/prod.env.example`

## Запуск

### Dev

```bash
cd deploy/adult
cp env/dev.env.example env/runtime.env

docker compose \
  -f compose.yaml \
  -f compose.dev.yaml \
  --env-file env/runtime.env \
  up -d --build
```

### Prod baseline

```bash
cd deploy/adult
cp env/prod.env.example env/runtime.env

docker compose \
  -f compose.yaml \
  -f compose.prod.yaml \
  --env-file env/runtime.env \
  up -d --build
```

## Reverse proxy routing

`deploy/adult/nginx/conf.d/genomeai.conf` задаёт routing:

- `/api/*` → `backend-api`
- `/metrics` → `backend-api`
- `/healthz` / `/readyz` → `backend-api`
- `/` → `web-frontend`

Это делает web frontend default UI target и убирает direct-public exposure backend как user-facing entrypoint.

## Worker / scheduler

На этом шаге worker и scheduler вынесены в отдельные сервисы:

- `scripts/service_worker.py`
- `scripts/service_scheduler.py`

Они публикуют heartbeat files:

- `/tmp/genomeai-worker-heartbeat.json`
- `/tmp/genomeai-scheduler-heartbeat.json`

Healthcheck контейнера валидирует свежесть heartbeat, а не просто факт старта процесса.

## PostgreSQL / Redis / MinIO

Эти сервисы введены как **deployment contour baseline**.

Важно:

- PostgreSQL и Redis уже присутствуют как обязательные platform services контуры.
- Backend persistence migration в отдельный runtime data plane **не считается завершённой этим шагом**.
- MinIO вводится как S3-compatible artifact storage baseline для on-prem production contour.

## Structured logs / metrics

- API и services используют уже существующий structured logger.
- Nginx access logs переведены в JSON log format.
- Для metrics добавлен Prometheus scrape baseline (`deploy/adult/prometheus/prometheus.yml`).
- Этот шаг не обещает full enterprise observability suite, но фиксирует production-capable baseline.

## Backup / restore

Host-driven ops scripts:

- `deploy/adult/ops/backup_host.sh`
- `deploy/adult/ops/restore_host.sh`

На этом шаге backup/restore покрывают:

- PostgreSQL dump;
- Redis snapshot export;
- runtime artifacts tarball;
- manifest с timestamp/profile.

## K8s baseline

Добавлен минимальный baseline для дальнейшего k8s path:

- `deploy/adult/k8s/kustomization.yaml`
- `deploy/adult/k8s/namespace.yaml`
- `deploy/adult/k8s/configmap-env.example.yaml`
- `deploy/adult/k8s/ingress.example.yaml`

Это **не production-certified k8s deployment**, а baseline для следующего шага без потери topology discipline.

## Что intentionally не обещается

Этот шаг **не утверждает**:

- что PostgreSQL уже стал единственным источником правды backend runtime-state;
- что Redis уже является production queue source для domain jobs;
- что есть подтверждённый SLA;
- что сделана HA/DR архитектура enterprise-уровня.

Но этот шаг **фиксирует взрослый deployment contour**, на который уже можно опираться для дальнейшей hardening/migration работы.
