# Operations runbook — install / upgrade / rollback / incidents / support

Дата: 2026-04-14
Статус: operational companion to `docs/deployment_full_guide.md`.

Этот документ нужен оператору/DevOps/поддержке, когда стек уже существует и требуется повторяемая эксплуатация:

- start/stop/restart
- upgrade
- rollback
- incident-first diagnostics
- backup/restore
- support bundle collection
- quick go/no-go checks

---

## 1. Быстрые правила эксплуатации

1. Не редактировать контейнеры вручную внутри runtime.
2. Все изменения — через git/release + `deploy/adult/env/runtime.env` + secrets files.
3. Перед upgrade всегда делать backup и support bundle.
4. Rollback без backup запрещён.
5. Внешне публиковать только reverse proxy.
6. Для stage/prod использовать file-based secrets, а не plain secrets в compose.

---

## 2. Стандартные команды управления стеком

### Старт

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
```

### Остановка

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env down
```

### Перезапуск без rebuild

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d
```

### Статус

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env ps
```

### Логи

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env logs --tail=200 backend-api
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env logs --tail=200 web-frontend
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env logs --tail=200 worker
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env logs --tail=200 scheduler
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env logs --tail=200 reverse-proxy
```

---

## 3. Post-start verification

```bash
bash /opt/genomeai/app/repo/deploy/adult/ops/post_deploy_smoke.sh prod
```

Если этот smoke падает, customer traffic считать неподтверждённым.

---

## 4. Upgrade runbook

### 4.1 Pre-upgrade checklist

- [ ] change ticket открыт
- [ ] backup сделан
- [ ] support bundle сделан
- [ ] target release tag известен
- [ ] rollback target release tag известен
- [ ] operator on-call назначен
- [ ] окно работ согласовано

### 4.2 Выполнение

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/backup_host.sh
bash deploy/adult/ops/collect_support_bundle.sh prod

git fetch --all
git checkout <TARGET_RELEASE_TAG>

cd deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
bash ops/post_deploy_smoke.sh prod
```

### 4.3 Условия успеха

- все сервисы `healthy`
- smoke passed
- web UI доступен
- `/api/app/v1/auth/me` и ключевые read paths отвечают
- worker/scheduler healthy

---

## 5. Rollback runbook

### 5.1 Когда rollback обязателен

- smoke падает после upgrade
- бизнес-критичный API недоступен
- web UI недоступен
- auth/session broken
- риск потери traceability / audit
- data plane inconsistency suspected

### 5.2 Rollback по release

```bash
cd /opt/genomeai/app/repo
git checkout <PREVIOUS_RELEASE_TAG>
cd deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
bash ops/post_deploy_smoke.sh prod
```

### 5.3 Rollback по backup

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/restore_host.sh /path/to/backup_dir
bash deploy/adult/ops/post_deploy_smoke.sh prod
```

Rollback считать завершённым только после smoke.

---

## 6. Incident-first diagnostics

### Симптом 1: web UI не отвечает

1. `docker compose ps`
2. `reverse-proxy` logs
3. `web-frontend` logs
4. `curl https://<host>/healthz`
5. `curl https://<host>/api/healthz`

### Симптом 2: login/auth broken

1. проверить `backend-api` logs
2. проверить secrets files для auth keys
3. проверить `GENOMEAI_WEB_SECRET_FILE`, `GENOMEAI_AUTH_SIGNING_KEY_FILE`, `GENOMEAI_AUTH_REFRESH_HMAC_KEY_FILE`
4. выполнить smoke и собрать support bundle

### Симптом 3: jobs не исполняются

1. `worker` logs
2. `scheduler` logs
3. heartbeat files
4. postgres/redis health

### Симптом 4: API отвечает 5xx

1. `backend-api` logs
2. `curl /readyz`
3. `curl /metrics/prometheus`
4. проверить postgres/redis/minio logs

---

## 7. Backup / restore discipline

### Backup

```bash
bash /opt/genomeai/app/repo/deploy/adult/ops/backup_host.sh
```

### Restore

```bash
bash /opt/genomeai/app/repo/deploy/adult/ops/restore_host.sh /path/to/backup_dir
```

### Restore drill

```bash
cd /opt/genomeai/app/repo
bash scripts/run_backup_restore_drill.sh
```

---

## 8. Support bundle discipline

### Быстрый сбор из running stack

```bash
bash /opt/genomeai/app/repo/deploy/adult/ops/collect_support_bundle.sh prod
```

### Что вложить в incident ticket

- support bundle path
- release tag / commit
- env profile (`stage`/`prod`)
- время инцидента UTC
- affected services
- smoke output
- последние 200 строк логов проблемного сервиса

---

## 9. Android operational baseline

Android не деплоится как server service, но должен учитываться в release discipline:

- release build source lives in `mobile_android/`
- API base URL должен указывать на production reverse proxy host
- mobile release должен быть привязан к тому же server release window
- при critical server rollback команда должна проверить совместимость mobile auth/sync flows

Smoke для Android baseline:

```bash
bash /opt/genomeai/app/repo/scripts/smoke_t32_08_android_field_app.sh
bash /opt/genomeai/app/repo/scripts/smoke_t32_08a_android_offline_sync_contract.sh
bash /opt/genomeai/app/repo/scripts/smoke_t32_09_android_offline_sync_model.sh
```

---

## 10. Quick go/no-go checklist

### GO

- [ ] backup completed
- [ ] support bundle completed
- [ ] target release fetched
- [ ] secrets unchanged or rotated intentionally
- [ ] compose up completed
- [ ] post_deploy_smoke passed
- [ ] operator signoff recorded

### NO-GO

- [ ] smoke failed
- [ ] one or more services unhealthy
- [ ] auth boundary broken
- [ ] no rollback target
- [ ] no backup/support bundle

---

## 11. Минимальные артефакты после каждого production change

Сохранять:

- release tag / commit
- deployment timestamp UTC
- backup dir
- support bundle zip path
- smoke output
- operator signoff
- incident/ref ticket ids if any

## Graceful shutdown timeout (uvicorn)

Backend launched via `python -m genomeai.app_launcher` passes
`--timeout-graceful-shutdown` to uvicorn. Default: `10` seconds. Override
via env:

    GENOMEAI_WEB_SHUTDOWN_TIMEOUT=20

App-level path: FastAPI lifespan shutdown handler calls
`web_cabinet.ai.endpoints.insights_stream.signal_shutdown()`, which wakes
all live SSE generators on `/api/ai/insights/events/stream`; fast-path
shutdown completes in <1 s (smoke-proof in `artifacts/_ci/sse_shutdown_smoke.log`
after running `python scripts/smoke_sse_shutdown.py`). The uvicorn flag is a
safety-net for any streaming endpoint that does not (yet) observe the
shutdown event.

If the backend ever appears to hang on SIGTERM:

1. Check `ss -tlnp | grep :8000` — listen socket should be gone.
2. Check `ss -anp | grep :8000` — count ESTABLISHED connections; non-zero
   means streaming clients are stuck.
3. Inspect logs (`/tmp/uvicorn.log` or `logs_dir/backend_uvicorn.log`).
4. Worst case — `kill -KILL` the process; investigate which streaming
   endpoint failed to honor the shutdown event.
