# Полная инструкция по развёртыванию GenomeAI AgroAnimals

Дата: 2026-04-14
Статус: production-oriented deployment guide для on-prem / enterprise / customer environments.

Этот документ — **основная пошаговая инструкция** по развёртыванию всей системы целиком:

- reverse proxy / TLS;
- `web_app` (Next.js);
- backend API (`web_cabinet.app`, canonical `/api/app/v1/*`);
- `worker`;
- `scheduler`;
- PostgreSQL;
- Redis;
- artifact storage (MinIO);
- metrics / structured logs / backup / restore;
- Android build/distribution baseline.

Документ рассчитан на новую техническую команду, которая **не получит устных пояснений от разработчика**. Если шаг не описан здесь, он не должен считаться обязательным для первичного запуска.

> Важно: текущий production contour зафиксирован в `deploy/adult/`. Старый `deploy/` можно использовать как исторический/compatibility-материал, но **не как целевой multi-service deployment baseline**.

---

## 1. Что именно разворачивается

Целевой production contour состоит из следующих сервисов.

| Сервис | Назначение | Базовый порт/endpoint |
|---|---|---|
| `reverse-proxy` | единая точка входа HTTP/HTTPS | `80/443` |
| `web-frontend` | пользовательский web UI (`web_app`) | `3000` internal |
| `backend-api` | FastAPI / canonical API / admin-support surface | `8000` internal |
| `worker` | выполнение job queue и фоновых задач | heartbeat file |
| `scheduler` | периодические scheduling jobs | heartbeat file |
| `postgres` | реляционная БД production contour | `5432` internal |
| `redis` | cache / coordination / future queue baseline | `6379` internal |
| `artifact-storage` | MinIO, S3-compatible storage | `9000/9001` internal |
| `prometheus` | metrics scraping baseline | `9090` internal |

Внутри `deploy/adult/compose.yaml` сервисы уже разведены по сетям:

- `edge_net` — ingress edge;
- `app_net` — web + API;
- `data_net` — API/worker/scheduler + postgres/redis/minio;
- `ops_net` — API/worker/scheduler + Prometheus.

---

## 2. Поддерживаемые профили окружений

Используются четыре профиля:

- `dev`
- `test`
- `stage`
- `prod`

Файлы:

- `deploy/adult/compose.yaml` — общая база;
- `deploy/adult/compose.dev.yaml`
- `deploy/adult/compose.test.yaml`
- `deploy/adult/compose.stage.yaml`
- `deploy/adult/compose.prod.yaml`

Файлы переменных окружения:

- `deploy/adult/env/dev.env.example`
- `deploy/adult/env/test.env.example`
- `deploy/adult/env/stage.env.example`
- `deploy/adult/env/prod.env.example`
- runtime copy: `deploy/adult/env/runtime.env`

### Как выбирать профиль

| Сценарий | Профиль |
|---|---|
| локальная разработка и ручная проверка | `dev` |
| CI / automated verification / pre-merge | `test` |
| customer staging / pre-prod rehearsal | `stage` |
| production контур у клиента | `prod` |

---

## 3. Требования к серверу и сети

### 3.1 Минимум для stage/prod baseline

Рекомендованный baseline для первой production-like установки:

- ОС: Ubuntu 24.04 LTS или эквивалентный Linux x86_64;
- CPU: 8 vCPU;
- RAM: 16 GB;
- Disk: 150+ GB SSD/NVMe;
- Docker Engine + Docker Compose plugin;
- `git`, `curl`, `jq`, `tar`, `openssl`.

Это не SLA-гарантия и не sizing для любого кластера. Для реального customer deployment sizing должен проверяться отдельно по числу users/jobs/model runs/artifact growth.

### 3.2 Открытые порты

Снаружи должны быть доступны только:

- `80/tcp` — HTTP redirect / bootstrap (если используется);
- `443/tcp` — основной HTTPS endpoint.

Внутренние сервисы (`8000`, `5432`, `6379`, `9000`, `9090`, `3000`) **не должны** публиковаться наружу без отдельного решения по безопасности.

### 3.3 Пример host layout

Рекомендуемый layout на сервере:

```text
/opt/genomeai/
  app/
    repo/                     # git checkout / release source
    deploy/adult/
    runtime/
      artifacts/
      web_storage/
      logs/
      backups/
    tls/
    releases/
```

Команды:

```bash
sudo mkdir -p /opt/genomeai/app
sudo chown -R $USER:$USER /opt/genomeai/app
cd /opt/genomeai/app
```

---

## 4. Подготовка окружения на сервере

### 4.1 Установка Docker Engine и Compose plugin

Пример для Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release jq git unzip tar

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker

docker version
docker compose version
```

### 4.2 Проверка базовых утилит

```bash
command -v git
command -v curl
command -v jq
command -v tar
command -v openssl
```

---

## 5. Получение исходников и подготовка runtime путей

### 5.1 Git checkout

```bash
cd /opt/genomeai/app
git clone <REPOSITORY_URL> repo
cd repo
```

Для deployment по release archive:

```bash
cd /opt/genomeai/app
unzip genomeai_release.zip -d repo
cd repo
```

### 5.2 Создание runtime директорий

```bash
cd /opt/genomeai/app/repo
mkdir -p runtime/artifacts runtime/web_storage runtime/logs runtime/backups
mkdir -p deploy/adult/secrets
mkdir -p deploy/adult/env
```

---

## 6. Secrets и runtime env

### 6.1 Принцип

- `dev/test` могут использовать plain env values.
- `stage/prod` должны использовать **file-based secrets** через `*_FILE` pattern и каталог `deploy/adult/secrets/`.
- Секреты не коммитятся в git.

### 6.2 Какие secret files обязательны

Для `stage/prod` создайте файлы:

```bash
cd /opt/genomeai/app/repo/deploy/adult/secrets

cp genomeai_web_secret.example genomeai_web_secret
cp internal_service_token.example internal_service_token
cp auth_signing_key.example auth_signing_key
cp auth_refresh_hmac_key.example auth_refresh_hmac_key
cp postgres_password.example postgres_password
cp redis_password.example redis_password
cp minio_root_user.example minio_root_user
cp minio_root_password.example minio_root_password
```

Сгенерируйте реальные значения:

```bash
openssl rand -hex 32 > genomeai_web_secret
openssl rand -hex 32 > internal_service_token
openssl rand -hex 64 > auth_signing_key
openssl rand -hex 64 > auth_refresh_hmac_key
openssl rand -hex 24 > postgres_password
openssl rand -hex 24 > redis_password
printf 'genomeai\n' > minio_root_user
openssl rand -hex 24 > minio_root_password
chmod 600 *
```

### 6.3 Создание runtime env file

Пример для `prod`:

```bash
cd /opt/genomeai/app/repo/deploy/adult
cp env/prod.env.example env/runtime.env
```

Откройте `env/runtime.env` и задайте как минимум:

```dotenv
GENOMEAI_HTTP_PORT=80
GENOMEAI_HTTPS_PORT=443
GENOMEAI_WEB_BASE_URL=https://your.customer.host
GENOMEAI_API_BASE_URL=http://backend-api:8000

GENOMEAI_WEB_SECRET_FILE=/run/secrets/genomeai_web_secret
GENOMEAI_INTERNAL_SERVICE_TOKEN_FILE=/run/secrets/internal_service_token
GENOMEAI_AUTH_SIGNING_KEY_FILE=/run/secrets/auth_signing_key
GENOMEAI_AUTH_REFRESH_HMAC_KEY_FILE=/run/secrets/auth_refresh_hmac_key

POSTGRES_DB=genomeai
POSTGRES_USER=genomeai
POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
REDIS_PASSWORD_FILE=/run/secrets/redis_password
MINIO_ROOT_USER_FILE=/run/secrets/minio_root_user
MINIO_ROOT_PASSWORD_FILE=/run/secrets/minio_root_password
MINIO_BUCKET_ARTIFACTS=genomeai-artifacts
```

### 6.4 Проверка secrets loader pattern

```bash
bash deploy/adult/ops/run_with_runtime_secrets.sh env | rg 'GENOMEAI_|POSTGRES|REDIS|MINIO'
```

Если одновременно заданы `FOO` и `FOO_FILE`, wrapper должен упасть с ошибкой.

---

## 7. TLS и reverse proxy

### 7.1 Базовые конфиги

Используются:

- `deploy/adult/nginx/nginx.conf`
- `deploy/adult/nginx/conf.d/genomeai.conf`
- `deploy/adult/security/security_headers.conf`
- `deploy/adult/security/tls_server.conf.example`

### 7.2 Подготовка сертификатов

Каталог TLS в compose — volume `tls_certs`, который мапится в `/etc/nginx/tls`.

Для on-prem baseline команда может использовать либо:

- корпоративный PKI/CA;
- customer-provided certificate;
- временный self-signed certificate для `stage`.

Пример self-signed для `stage`:

```bash
mkdir -p /opt/genomeai/app/tls
cd /opt/genomeai/app/tls
openssl req -x509 -nodes -days 365 -newkey rsa:4096 \
  -keyout tls.key \
  -out tls.crt \
  -subj "/CN=stage.example.invalid"
```

Затем разместите `tls.crt` и `tls.key` туда, где их ожидает runtime deployment policy. Если используется custom Nginx TLS overlay, не меняйте базовую топологию сервисов.

### 7.3 Что уже делает reverse proxy

- `/` → `web-frontend`
- `/api/*` → `backend-api`
- `/metrics/prometheus` → `backend-api`
- `/healthz` и `/readyz` → backend health/readiness

---

## 8. Первый запуск: dev / stage / prod

### 8.1 Dev

```bash
cd /opt/genomeai/app/repo/deploy/adult
cp env/dev.env.example env/runtime.env

docker compose \
  -f compose.yaml \
  -f compose.dev.yaml \
  --env-file env/runtime.env \
  up -d --build
```

### 8.2 Stage

```bash
cd /opt/genomeai/app/repo/deploy/adult
cp env/stage.env.example env/runtime.env
# затем отредактировать env/runtime.env под stage hostnames/secrets

docker compose \
  -f compose.yaml \
  -f compose.stage.yaml \
  --env-file env/runtime.env \
  up -d --build
```

### 8.3 Prod

```bash
cd /opt/genomeai/app/repo/deploy/adult
cp env/prod.env.example env/runtime.env
# затем отредактировать env/runtime.env под prod hostnames/secrets

docker compose \
  -f compose.yaml \
  -f compose.prod.yaml \
  --env-file env/runtime.env \
  up -d --build
```

### 8.4 Проверка статусов контейнеров

```bash
docker compose \
  -f deploy/adult/compose.yaml \
  -f deploy/adult/compose.prod.yaml \
  --env-file deploy/adult/env/runtime.env \
  ps
```

Ожидается статус `healthy` у:

- `reverse-proxy`
- `web-frontend`
- `backend-api`
- `worker`
- `scheduler`
- `postgres`
- `redis`
- `artifact-storage`
- `prometheus`

---

## 9. Post-deploy smoke checklist

### 9.1 Базовые HTTP проверки

```bash
curl -fsS http://127.0.0.1/healthz
curl -fsS http://127.0.0.1/readyz
curl -fsS http://127.0.0.1/api/healthz
curl -fsS http://127.0.0.1/api/readyz
curl -fsS http://127.0.0.1/metrics/prometheus | head
curl -fsS http://127.0.0.1/api/healthz | jq . || true
```

### 9.2 Автоматизированный smoke

Используйте helper script:

```bash
bash deploy/adult/ops/post_deploy_smoke.sh prod
```

или для stage:

```bash
bash deploy/adult/ops/post_deploy_smoke.sh stage
```

### 9.3 Repo-level deployment validator

```bash
bash scripts/smoke_t32_10_server_deployment.sh
bash scripts/smoke_t32_10a_production_security.sh
bash scripts/smoke_t32_13_deployment_full_guide.sh
```

---

## 10. Что должно быть проверено после первого запуска

### 10.1 Reverse proxy

- открывается `https://<host>/`
- открывается `https://<host>/healthz`
- открывается `https://<host>/readyz`
- `https://<host>/api/healthz` отвечает
- `https://<host>/metrics/prometheus` отвечает

### 10.2 Web frontend

- web UI доступен через reverse proxy
- `/api/healthz` и `/api/readyz` самого web frontend живут
- frontend не обращается напрямую к внутренним Python-модулям

### 10.3 Backend API

- canonical `/api/app/v1/*` доступен
- auth boundary доступен
- `/metrics/prometheus` отвечает
- structured logs идут в stdout/stderr контейнера

### 10.4 Background services

- worker и scheduler healthy
- heartbeat files обновляются
- job queue продолжает работать

### 10.5 Data plane

- postgres healthy
- redis healthy
- minio healthy
- bucket `MINIO_BUCKET_ARTIFACTS` создан

---

## 11. Рекомендуемая последовательность первичного customer deployment

### 11.1 Шаг 1 — Preflight

```bash
cd /opt/genomeai/app/repo
python scripts/validate_t32_10_server_deployment.py
python scripts/validate_t32_10a_production_security.py
python scripts/validate_t32_12_streamlit_removal.py
python scripts/validate_t32_12a_streamlit_legacy_cleanup.py
```

### 11.2 Шаг 2 — Security material

- создать secret files;
- положить TLS cert/key;
- заполнить `deploy/adult/env/runtime.env`.

### 11.3 Шаг 3 — Start stack

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
```

### 11.4 Шаг 4 — Post-deploy smoke

```bash
bash /opt/genomeai/app/repo/deploy/adult/ops/post_deploy_smoke.sh prod
```

### 11.5 Шаг 5 — Deployment record

Оператор должен сохранить:

- git commit / release archive hash;
- copy `env/runtime.env` без секретных значений;
- список service image digests;
- smoke output;
- backup path первой контрольной backup.

---

## 12. Upgrade procedure

### 12.1 Подготовка перед upgrade

1. Снять backup.
2. Собрать support bundle.
3. Проверить cutover / rollback readiness.
4. Подготовить release directory или новый git revision.

### 12.2 Снять backup

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/backup_host.sh
```

### 12.3 Собрать support bundle

```bash
bash deploy/adult/ops/collect_support_bundle.sh prod
```

### 12.4 Обновить код

```bash
cd /opt/genomeai/app/repo
git fetch --all
git checkout <RELEASE_TAG_OR_COMMIT>
```

Или обновить release archive в новой директории, затем переключить symlink/working directory по внутренней политике клиента.

### 12.5 Rebuild и rolling restart baseline

```bash
cd /opt/genomeai/app/repo/deploy/adult
docker compose \
  -f compose.yaml \
  -f compose.prod.yaml \
  --env-file env/runtime.env \
  up -d --build
```

### 12.6 Post-upgrade smoke

```bash
bash /opt/genomeai/app/repo/deploy/adult/ops/post_deploy_smoke.sh prod
```

### 12.7 Support verification

Сразу после upgrade проверьте:

- web login
- `/api/app/v1/auth/me`
- daily-summary screen
- profiles / reports screen
- background worker healthy
- scheduler healthy
- support bundle still collectable

---

## 13. Rollback procedure

> Rollback запрещён без заранее снятого backup.

### 13.1 Когда делать rollback

Rollback обязателен, если после upgrade:

- post-deploy smoke падает;
- `backend-api` или `web-frontend` не становятся healthy;
- возникает data corruption risk;
- auth boundary broken;
- pilot/customer critical path недоступен.

### 13.2 Логический rollback приложения

Если data plane не был мигрирован несовместимо, сначала попробуйте rollback по коду/образам:

```bash
cd /opt/genomeai/app/repo
git checkout <PREVIOUS_RELEASE_TAG>
cd deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
bash ops/post_deploy_smoke.sh prod
```

### 13.3 Data rollback

Если нужно восстановление артефактов/runtime-state:

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/restore_host.sh /opt/genomeai/app/repo/runtime/backups/<STAMP>
```

После restore снова прогоните:

```bash
bash deploy/adult/ops/post_deploy_smoke.sh prod
```

---

## 14. Backup / restore

### 14.1 Host-level backup

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/backup_host.sh
```

Что создаётся:

- `postgres.sql`
- `redis.rdb`
- `runtime_artifacts.tgz`
- `manifest.json`

### 14.2 Restore

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/restore_host.sh /path/to/backup_dir
```

### 14.3 Repo-level backup/restore drill

```bash
bash scripts/backup_restore_check.sh
bash scripts/run_backup_restore_drill.sh
```

### 14.4 Что нужно архивировать отдельно

Для customer environments храните вне основного runtime также:

- copy `deploy/adult/env/runtime.env` без secret values;
- checksum release archive / git commit;
- TLS cert metadata (не обязательно приватный ключ, зависит от customer policy);
- change ticket / deployment ticket.

---

## 15. Incident-first diagnostics

### 15.1 Если web UI не открывается

Проверить:

```bash
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env ps

docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=200 reverse-proxy
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=200 web-frontend
```

И затем:

```bash
curl -vk https://<host>/healthz
curl -vk https://<host>/api/healthz
```

### 15.2 Если backend unhealthy

```bash
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=300 backend-api
curl -fsS http://127.0.0.1:8000/readyz || true
```

### 15.3 Если фоновые задачи не идут

```bash
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=300 worker
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=300 scheduler
```

Проверить heartbeat/checks:

```bash
python scripts/check_heartbeat.py /tmp/genomeai-worker-heartbeat.json 120 || true
python scripts/check_heartbeat.py /tmp/genomeai-scheduler-heartbeat.json 180 || true
```

### 15.4 Если проблема в data plane

```bash
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=200 postgres
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=200 redis
docker compose -f deploy/adult/compose.yaml -f deploy/adult/compose.prod.yaml --env-file deploy/adult/env/runtime.env logs --tail=200 artifact-storage
```

### 15.5 Если нужен support bundle

```bash
bash deploy/adult/ops/collect_support_bundle.sh prod
```

---

## 16. Support bundle collection

### 16.1 Из running deployment contour

```bash
bash deploy/adult/ops/collect_support_bundle.sh prod
```

### 16.2 Напрямую через CLI внутри репозитория

```bash
PYTHONPATH=src python -m genomeai.cli support-bundle \
  --project-root . \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --db-path web_cabinet/storage/web.db \
  --out artifacts/support_bundles/support_bundle_manual.zip
```

### 16.3 Что передавать в support

Минимальный комплект:

- support bundle zip;
- текущий commit/release tag;
- `docker compose ps` output;
- последние 200 строк логов проблемного сервиса;
- smoke output и время инцидента.

---

## 17. Android build / distribution baseline

Android-контур — это отдельное приложение `mobile_android/`, а не web wrapper.

### 17.1 Что уже есть в репозитории

- Kotlin / Jetpack Compose проект в `mobile_android/`
- AGP / Kotlin build files
- separate mobile auth / sync / offline baseline
- pure-Kotlin smoke for contracts and offline model

### 17.2 Ограничение текущего baseline

В репозитории **нет checked-in Gradle wrapper**, поэтому production APK/AAB build должен выполняться либо:

- через Android Studio с импортом `mobile_android/`, либо
- через корпоративную Android CI/CD среду, где Gradle уже provisioned.

Это ограничение нужно учитывать честно; оно не мешает server deployment, но влияет на способ сборки Android пакета.

### 17.3 Рекомендуемые требования для Android build workstation

- Android Studio Iguana или новее;
- JDK 17;
- Android SDK Platform 35;
- Android Build Tools 35.x;
- доступ к Maven Central / Google Maven.

### 17.4 Сборка baseline через Android Studio

1. Открыть Android Studio.
2. `Open` → выбрать каталог `mobile_android/`.
3. Дождаться sync.
4. Проверить `Build Variants` (`debug`/`release`).
5. Собрать debug build.
6. Для release distribution подготовить signing config по политике клиента.

### 17.5 Что нужно зафиксировать в customer/pilot distribution

- `applicationId`
- `versionName`
- `versionCode`
- API base URL / environment profile
- подпись release build
- кто утвердил мобильный build для конкретного pilot/customer environment

### 17.6 Mobile smoke

```bash
bash scripts/smoke_t32_08_android_field_app.sh
bash scripts/smoke_t32_08a_android_offline_sync_contract.sh
bash scripts/smoke_t32_09_android_offline_sync_model.sh
```

---

## 18. K8s baseline

Kubernetes baseline зафиксирован как skeleton в:

- `deploy/adult/k8s/kustomization.yaml`
- `deploy/adult/k8s/namespace.yaml`
- `deploy/adult/k8s/configmap-env.example.yaml`
- `deploy/adult/k8s/secret.example.yaml`
- `deploy/adult/k8s/networkpolicy.example.yaml`
- `deploy/adult/k8s/ingress.example.yaml`

Текущий guide ориентирован в первую очередь на Docker Compose on-prem deployment. K8s baseline используйте только если customer environment уже стандартизован под Kubernetes.

---

## 19. Что новая команда должна сохранить после успешного деплоя

Минимальный deployment record:

- дата/время деплоя;
- customer/stage/prod environment id;
- git commit / release tag;
- compose overlay profile;
- runtime env checksum;
- список secret files (без содержимого);
- post-deploy smoke result;
- backup location;
- support bundle location;
- operator signoff.

---

## 20. Минимальная команда для повторения критичных операций

### Установка / первый старт

```bash
cd /opt/genomeai/app/repo/deploy/adult
cp env/prod.env.example env/runtime.env
# заполнить env/runtime.env и secrets/
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
bash ops/post_deploy_smoke.sh prod
```

### Upgrade

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/backup_host.sh
bash deploy/adult/ops/collect_support_bundle.sh prod
git checkout <NEW_RELEASE>
cd deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
bash ops/post_deploy_smoke.sh prod
```

### Rollback

```bash
cd /opt/genomeai/app/repo
git checkout <PREVIOUS_RELEASE>
cd deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/runtime.env up -d --build
bash ops/post_deploy_smoke.sh prod
```

или, если нужен restore состояния:

```bash
cd /opt/genomeai/app/repo
bash deploy/adult/ops/restore_host.sh /path/to/backup_dir
bash deploy/adult/ops/post_deploy_smoke.sh prod
```

### Диагностика

```bash
bash deploy/adult/ops/post_deploy_smoke.sh prod
bash deploy/adult/ops/collect_support_bundle.sh prod
```
