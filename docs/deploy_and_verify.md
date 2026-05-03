# Полная инструкция: развертывание и проверка GenomeAI AgroAnimals

Документ объединяет **развертывание** (локально и on‑prem), **проверку работоспособности** (offline‑core и web‑cabinet), а также базовые процедуры эксплуатации (логи, бэкапы, совместимость артефактов).

> Важно: архитектурный принцип проекта — **web‑cabinet ничего не “считает”**. Веб лишь ставит задачи и вызывает **offline‑core CLI** (`genomeai ...`).

---

## 0) Термины и версияция артефактов

Сквозные версии (используются в путях `artifacts/`):
- `data_version` — версия данных (канонические таблицы)
- `qc_run` — прогон QC
- `model_version` — версия обученной модели
- `scoring_run` — прогон скоринга
- `report_version` — версия отчёта (LLM или fallback)
- `decision_log` — журнал решений (в т.ч. user/when/why)

Артефакты хранятся в:
- `artifacts/<data_version>/...`

См. также: `docs/data_contracts.md`, `docs/pilot_pack.md`, `docs/target/nfr_target.md`.

---

## 1) Варианты развертывания

### Вариант A — локально (developer / demo)
Подходит для разработки и демонстраций на ноутбуке.

**Требования:**
- Python **3.11+**
- Linux/macOS (Windows — через WSL2 рекомендуется)

### Вариант B — on‑prem (рекомендуемо) через Docker Compose
Подходит для пилота и эксплуатации.

**Требования:**
- Linux x86_64
- Docker Engine + Docker Compose plugin
- Рекомендовано: 4 CPU / 8 GB RAM
- Диск: от 20 GB (зависит от объёма данных и числа версий)

Полный runbook on‑prem: `docs/runbook_onprem.md`.

---

## 2) Структура репозитория (важно для эксплуатации)

- `src/` — **offline‑core** (логика: ingest/qc/train/score/report/pack/decision/backup/restore)
- `web_cabinet/` — **backend/операционный слой** (очередь задач, запуск CLI, RBAC/audit, healthchecks; веб ничего не считает)
- `web_app/` — standalone React/Next.js web frontend; продуктовый UI после T32-12.
- `configs/` — контракты и мэппинги
- `data/examples/` — демо‑данные
- `artifacts/` — артефакты версий (по умолчанию в локальном запуске)
- `runtime/` — рекомендуемое место persist‑данных для Docker (`runtime/artifacts`, `runtime/web_storage`)

---

## 3) Развертывание: локально (Python)

### 3.1 Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Проверка, что CLI доступен:

```bash
genomeai --help
```

### 3.2 Быстрый офлайн‑прогон (A1..A6)

Команда создаст новый `data_version` и выполнит полный цикл: ingest → qc → train → score → report → pack.

```bash
DV="dv_demo_$(date -u +%Y%m%d_%H%M%S)"
python -m genomeai smoke --out-version "$DV" --artifacts artifacts

# Посмотреть артефакты
ls -la artifacts/$DV
cat artifacts/$DV/versions.json
```

### 3.3 Локальный single-entry запуск

Рекомендуемый путь для пользователя и support:

```bash
python -m genomeai.app_launcher --open-browser
# или
bash scripts/run_single_entry_local.sh
```

Открыть UI: `http://localhost:${GENOMEAI_WEB_UI_PORT:-3000}` — это **основной пользовательский вход**.

FastAPI backend запускается рядом и остаётся доступным как hidden fallback/internal admin-debug surface на `http://localhost:8000`.

Демо‑учётки: `admin/admin`, `operator/operator`, `viewer/viewer`, `director/director`, `zootech/zootech`, `vet/vet`.

### 3.4 Fallback/backend-only запуск (при необходимости)

```bash
# важно: без --reload (иначе worker может дублироваться)
uvicorn web_cabinet.app:app --host 0.0.0.0 --port 8000
```

Этот путь нужен только для support/admin/debug и backward compatibility, а не для ежедневного пользовательского сценария.

---

## 4) Развертывание: on‑prem (Docker Compose)

Подробно: `docs/runbook_onprem.md`. Ниже — короткая, но полная процедура.

### 4.1 Рекомендуемый layout на сервере

```text
/opt/genomeai/
  repo/                      # исходники
  runtime/
    artifacts/
    web_storage/
  .env
```

### 4.2 Подготовка

```bash
sudo mkdir -p /opt/genomeai
sudo chown -R $USER:$USER /opt/genomeai

cd /opt/genomeai
# либо git clone вашего репо, либо распаковка архива
mkdir -p runtime/artifacts runtime/web_storage
cp repo/deploy/.env.example .env
```

### 4.3 Настройка `.env`

Обязательное:
- `GENOMEAI_DEPLOY_PROFILE=dev|prod` — профиль compose и startup guardrails
- `GENOMEAI_WEB_SECRET` **или** `GENOMEAI_WEB_SECRET_FILE` — секрет сессий

Опционально:
- `OPENAI_API_KEY` или `OPENAI_API_KEY_FILE` — включит LLM‑режим в отчётах (без ключа работает fallback)
- `GENOMEAI_WEB_MAX_UPLOAD_MB` — лимит размера файла данных (MB, default 200)
- `GENOMEAI_WEB_MAX_MAPPING_MB` — лимит размера мэппинга/конфига (MB, default 5)
- `GENOMEAI_JOB_TIMEOUT_SEC` — таймаут выполнения джоба (sec, default 1800)
- `GENOMEAI_CONNECTOR_RECOVERY_QUEUE_LIMIT` — лимит очереди recovery для коннекторов (default 5)
- `GENOMEAI_WEB_PORT` — порт backend fallback на хосте (default 8000)
- `GENOMEAI_WEB_UI_PORT` — порт standalone web frontend на хосте (default 3000)
- `GENOMEAI_WEB_PUBLIC_URL` — optional public URL standalone web frontend

Поведение hardening:
- в `prod` запуск блокируется, если секрет не задан, слишком короткий или равен `dev-secret-change-me`;
- `_FILE` переменные читаются на старте и дают понятную ошибку, если файл секрета отсутствует или пуст;
- compose-профиль `prod` включает `read_only`, `tmpfs /tmp`, `no-new-privileges`, `cap_drop: [ALL]` и healthcheck по `/readyz`.

### 4.4 Запуск

```bash
cd /opt/genomeai/repo

docker compose --env-file /opt/genomeai/.env --profile dev -f deploy/docker-compose.yml up -d --build

docker compose -f deploy/docker-compose.yml ps
curl -sS http://localhost:${GENOMEAI_WEB_PORT:-8000}/healthz
curl -sS http://localhost:${GENOMEAI_WEB_PORT:-8000}/readyz

# Primary user entry
echo "Open http://localhost:${GENOMEAI_WEB_UI_PORT:-3000}"

# Прод-режим (жестче, старт блокируется при небезопасном секрете)
# docker compose --env-file /opt/genomeai/.env --profile prod -f deploy/docker-compose.yml up -d --build
```

---

## 5) Проверка работоспособности (verification)

Ниже — **проверяемые** шаги. Их можно использовать как чек‑лист при установке.

### 5.1 Быстрый автоматический smoke (рекомендуется)

Локально (без Docker):

```bash
pip install -e .
./scripts/smoke_all.sh
```

Этот сценарий выполняет:
- `scripts/smoke_offline.sh` — офлайн полный цикл
- `scripts/smoke_web.sh` — web smoke (временный workdir)
- `scripts/backup_restore_check.sh` — backup→wipe→restore→verify



### 5.2 Проверка web UI (login → navigation → export)

1) Поднимите backend (`uvicorn ...` или Docker) и убедитесь в `readyz`.
2) Поднимите web frontend и backend.

3) В UI:
- логин под `operator` (пароль по умолчанию тоже `operator`);
- также доступны демо‑аккаунты: `admin/admin`, `viewer/viewer`, `director/director`, `zootech/zootech`, `vet/vet`;
- откройте ключевые страницы (`/daily-summary`, `/alerts`, `/worklists`, `/reports`);
- выполните экспорт отчёта и убедитесь, что файл скачался;
- убедитесь, что ошибки человекочитаемы (если нет артефактов — есть подсказка какие команды запустить).

Если логин не проходит (например, после переносов старой `web.db`):
- остановите UI/backend;
- удалите `web_cabinet/storage/web.db` (будет создан заново с демо‑пользователями);
- запустите UI/backend повторно.


### 5.2 Проверка web endpoints (health/ready/observability)

Если веб уже поднят (локально или docker):

```bash
# BASE_URL можно переопределить (например, http://server:8000)
BASE_URL="http://localhost:${GENOMEAI_WEB_PORT:-8000}" ./scripts/verify_web_endpoints.sh
```

Ожидаем:
- `/healthz` → `{"status":"ok"}`
- `/readyz` → `{"status":"ready"...}`
- `/api/observability` → JSON с uptime + агрегатами по job

### 5.3 Проверка NFR‑контролей (лимиты/таймауты)

**Лимиты upload:**
1) В `.env` выставьте маленькие лимиты, напр. `GENOMEAI_WEB_MAX_UPLOAD_MB=1`
2) Перезапустите сервис
3) Загрузите файл > 1MB → ожидаем HTTP **413 Payload Too Large**.

**Таймаут job:**
- В `.env` выставьте `GENOMEAI_JOB_TIMEOUT_SEC=1`
- Запустите long‑job (в тестах используется `genomeai sleep`)
- Ожидаем статус job = failed, exit_code=124 и ops‑алерт `ops.job_failed`.

### 5.4 Проверка полного цикла через web frontend (single-entry)

1) Логин в web frontend под `operator`.
2) Выполните путь `Upload & Ingest → Jobs Center → QC → Train → Score → Report → Decisions → Tasks / Workflow → Pilot Pack`.
3) Убедитесь, что:
   - переход в internal admin UI не требуется;
   - появляются записи в Jobs Center / workflow;
   - артефакты создаются в `artifacts/<data_version>/...`;
   - отчёт формируется даже без LLM-ключа (fallback).

---

## 6) Миграция Offline → Web (Pilot Pack)

Для передачи результатов с “офлайн машины” в веб‑кабинет используется **Pilot Pack**.

- Документация: `docs/pilot_pack.md`
- Миграционный план: `docs/target/migration_offline_to_web.md`

Команды:

```bash
# 1) На офлайн‑контуре собрать pack (или использовать genomeai smoke)
python -m genomeai smoke --out-version dv_pilot_001 --artifacts artifacts

# 2) Импорт в target‑storage (на веб‑контуре)
python -m genomeai import-pack --pack-zip <PATH_TO_PACK_ZIP> --artifacts runtime/artifacts

# 3) E2E smoke миграции
python -m genomeai smoke-migration --artifacts runtime/artifacts
```

---

## 7) Логи, алерты, наблюдаемость

Где смотреть:
- Docker: `docker compose logs -f`
- Логи джобов: `runtime/web_storage/logs/` (или `web_cabinet/storage/logs/` при локальном запуске)
- В UI: **Tasks & Logs**
- Ops‑алерты: Alert Center v2 (например `ops.job_failed`)
- Метрики (минимум): `GET /api/observability`

---

## 8) Backup/Restore

### 8.1 Логический backup (zip)

```bash
python -m genomeai backup --artifacts runtime/artifacts --web-storage runtime/web_storage
```

### 8.2 Restore

```bash
python -m genomeai restore --backup <backup.zip> --artifacts runtime/artifacts --web-storage runtime/web_storage --force
```

Сценарий проверки (делает всё автоматически):

```bash
./scripts/backup_restore_check.sh
```

---

## 9) Базовая безопасность (минимум для пилота)

1) **Поменять** `GENOMEAI_WEB_SECRET`.
2) **Сменить пароли демо‑аккаунтов** (или удалить демо‑БД и создать свои учётки).

Простой способ смены пароля напрямую в sqlite:

```bash
python - <<'PY'
from web_cabinet.auth import hash_password
import sqlite3

DB='runtime/web_storage/web.db'  # либо путь к вашему web.db
TENANT='default'
USER='admin'
NEW_PASSWORD='CHANGE_ME_NOW'

conn=sqlite3.connect(DB)
conn.row_factory=sqlite3.Row
ph=hash_password(NEW_PASSWORD)
cur=conn.execute('UPDATE users_v2 SET password_hash=? WHERE tenant_id=? AND username=?', (ph, TENANT, USER))
conn.commit()
print('updated:', cur.rowcount)
conn.close()
PY
```

3) Для пилота желательно поставить reverse‑proxy (nginx) и включить TLS.
4) Доступ к `runtime/` ограничить правами ОС (chmod/chown), регулярные бэкапы.

---

## 10) Troubleshooting (частые проблемы)

- **Порт занят**: поменяйте `GENOMEAI_WEB_PORT`.
- **Ready=false**: проверьте права на `runtime/`, наличие `web.db`, логи контейнера.
- **Большие файлы не грузятся**: проверьте `GENOMEAI_WEB_MAX_UPLOAD_MB`.
- **Job падает по таймауту**: увеличьте `GENOMEAI_JOB_TIMEOUT_SEC` или оптимизируйте расчёты.
- **LLM отчёт не строится**: без `OPENAI_API_KEY` отчёт строится в fallback — это нормально.
