# Runbook (On-Prem) — GenomeAI AgroAnimals

Дата: 2025-12-23

Этот документ описывает повторяемое развертывание **на on-prem** в варианте **Docker Compose** (рекомендуемый путь), а также процедуры **backup/restore** и smoke-проверки.

## 1) Компоненты и пути хранения

### Компоненты

1) **offline-core** (Python пакет `genomeai`) — выполняет ingest/qc/train/score/report/pack/decision/backup/restore.
2) **web frontend** (`web_app`) — основной пользовательский UI (single-entry).
3) **web-cabinet** (FastAPI, `web_cabinet`) — backend API + hidden fallback/internal admin-debug surface. Веб ничего не “считает”, он запускает offline-core через CLI.
4) **Очередь задач** — sqlite `web.db` в `web_storage/` и in-process worker (один поток) в backend-сервисе.

### Директории данных (persist)

В Docker Compose мы монтируем два каталога на хосте:

- `runtime/artifacts/` — все артефакты и версии: `data_version/qc_run/model_version/scoring_run/report_version/...`
- `runtime/web_storage/` — `web.db` (sqlite), `uploads/`, `logs/`

## 2) Требования

**Минимум:**

- Linux x86_64
- Docker Engine + Docker Compose plugin
- 4 CPU / 8 GB RAM (для baseline ML)
- Диск: от 20 GB (зависит от объёмов данных/числа версий)

**Сетевые требования:**

- HTTP доступ к порту `${GENOMEAI_WEB_UI_PORT:-3000}` для пользователей (web primary entry)
- Порт 8000 рекомендуется оставлять для support/admin/debug или проксировать как internal-only fallback

## 3) Установка и запуск (Docker Compose)

### 3.1 Подготовка каталога

Single-entry модель: пользователи открывают **web frontend**; FastAPI UI сохраняется как fallback/internal surface и не нужен для ежедневного пользовательского сценария.

Рекомендуемый layout на сервере:

```text
/opt/genomeai/
  repo/                      # исходники
  runtime/
    artifacts/
    web_storage/
  .env
```

Пример:

```bash
sudo mkdir -p /opt/genomeai
sudo chown -R $USER:$USER /opt/genomeai

cd /opt/genomeai
git clone <ВАШ-РЕПОЗИТОРИЙ> repo
mkdir -p runtime/artifacts runtime/web_storage
```

### 3.2 Конфиги (.env)

Скопируйте шаблон и задайте секрет. Для web frontend используйте `GENOMEAI_WEB_UI_PORT` (по умолчанию 3000):

```bash
cd /opt/genomeai
cp repo/deploy/.env.example .env
```

Обязательные параметры:

- `GENOMEAI_WEB_SECRET` — секрет для cookie-сессий (поменять обязательно).
- `GENOMEAI_WEB_UI_PORT` — порт standalone web frontend (default 3000).

Опциональные:
- `GENOMEAI_WEB_PUBLIC_URL` — явный публичный URL standalone web frontend.

- `OPENAI_API_KEY` — только если хотите LLM режим в отчётах. Без ключа отчёт строится в fallback.
- `GENOMEAI_WEB_MAX_UPLOAD_MB` — лимит размера загружаемого файла данных (MB, default: 200).
- `GENOMEAI_WEB_MAX_MAPPING_MB` — лимит размера маппинга/конфига (MB, default: 5).
- `GENOMEAI_JOB_TIMEOUT_SEC` — таймаут выполнения джоба worker'ом (sec, default: 1800).

### 3.3 Запуск

```bash
cd /opt/genomeai/repo

docker compose --env-file /opt/genomeai/.env --profile dev -f deploy/docker-compose.yml up -d --build

# Проверка
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -n 50

# Backend healthchecks (должны вернуть 200)
curl -sS http://localhost:${GENOMEAI_WEB_PORT:-8000}/healthz
curl -sS http://localhost:${GENOMEAI_WEB_PORT:-8000}/readyz
```

UI будет доступен по адресу:

- `http://<server>:${GENOMEAI_WEB_UI_PORT:-3000}` — **основной пользовательский вход**
- `http://<server>:${GENOMEAI_WEB_PORT:-8000}` — hidden fallback/internal backend surface

Демо-пользователи (сменить перед пилотом):

- admin/admin
- operator/operator
- viewer/viewer

## 4) Обновление и откат

### Обновление

```bash
cd /opt/genomeai/repo
git pull
docker compose --env-file /opt/genomeai/.env -f deploy/docker-compose.yml up -d --build
```

### Откат

Самый простой вариант: checkout на нужный commit/tag и снова `up -d --build`.

## 5) Backup / Restore

Есть 2 уровня:

1) **Файловый** (tar/rsync) — забэкапить `runtime/artifacts` и `runtime/web_storage`.
2) **Логический** (рекомендуемый для MVP): `genomeai backup/restore` — один zip с sha256-manifest и проверкой.

### 5.1 Логический backup (zip)

```bash
cd /opt/genomeai/repo

docker compose -f deploy/docker-compose.yml exec -T web-dev \
  genomeai backup --artifacts /data/artifacts --web-storage /data/web_storage

# zip окажется на хосте в runtime/artifacts/backups/
ls -la /opt/genomeai/runtime/artifacts/backups
```

### 5.2 Логический restore (zip)

Рекомендуемая процедура:

1) Остановить сервис
2) Restore
3) Поднять сервис

```bash
cd /opt/genomeai/repo

docker compose -f deploy/docker-compose.yml down

BACKUP_ZIP="/data/artifacts/backups/backup_YYYYMMDD_HHMMSS.zip"

docker compose --env-file /opt/genomeai/.env --profile dev -f deploy/docker-compose.yml run --rm web-dev \
  genomeai restore --backup "$BACKUP_ZIP" --artifacts /data/artifacts --web-storage /data/web_storage --force

docker compose --env-file /opt/genomeai/.env --profile dev -f deploy/docker-compose.yml up -d
```

`restore` проверяет sha256 по manifest и возвращает `verified_files/total_files`.

## 6) Smoke-тесты

Smoke-тесты есть в двух вариантах:

### 6.1 Offline smoke (A1..A6)

```bash
cd /opt/genomeai/repo
./scripts/smoke_offline.sh
```

### 6.2 Legacy web smoke (через API + worker, parity/fallback)

```bash
cd /opt/genomeai/repo
./scripts/smoke_web.sh
```

### 6.3 Backup→Wipe→Restore→Verify

```bash
cd /opt/genomeai/repo
./scripts/backup_restore_check.sh
```

## 7) Конфигурация и переменные окружения

### Web frontend + backend

- `GENOMEAI_PROJECT_ROOT` — путь к корню репо (в контейнере `/app`).
- `GENOMEAI_ARTIFACTS_ROOT` — путь к артефактам (`/data/artifacts`).
- `GENOMEAI_WEB_STORAGE` — sqlite + uploads + logs (`/data/web_storage`).
- `GENOMEAI_WEB_SECRET` — секрет для сессий.
- `GENOMEAI_WEB_UI_PORT` — порт standalone web frontend.
- `GENOMEAI_WEB_PUBLIC_URL` — публичный URL standalone web frontend.

### Отчёты (LLM режим)

- `OPENAI_API_KEY` — если задан, можно включать `--mode llm`.

## 8) Известные ограничения (B0/B1)

- Очередь задач — sqlite и один worker в процессе веба (не распределённо).
- Если вы обновляетесь со старых сборок, где пароли были захэшированы bcrypt,
  проще всего удалить `runtime/web_storage/web.db`, чтобы сервис пересоздал
  демо-пользователей на pbkdf2_sha256 (или заведите пользователей заново).
- Для продакшн-пилота желательно настроить:
  - внешний reverse proxy (nginx) + TLS
  - смену дефолтных паролей
  - ротацию логов и плановый backup
