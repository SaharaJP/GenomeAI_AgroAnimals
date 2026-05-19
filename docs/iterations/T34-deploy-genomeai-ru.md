# T34 — Deploy production stack on genomeai.ru

**Дата:** 2026-05-19
**Цель:** поднять `deploy/adult/compose.yaml + compose.prod.yaml` стек на боевом домене `genomeai.ru` с TLS от Let's Encrypt и без default-credentials.
**Host:** `91.229.105.152` (текущий dev-сервер).
**Связанные доки:** `docs/deployment_full_guide.md` (полный baseline), `docs/operations_runbook.md`, CLAUDE.md §6/§7/§11.

---

## 0. Что уже подготовлено в репо

| Файл | Изменение |
|---|---|
| `deploy/adult/nginx/conf.d/genomeai.conf` | HTTPS server-block для `genomeai.ru` + `www → 301 → apex` + ACME-challenge location |
| `deploy/adult/env/prod.env.example` | `GENOMEAI_WEB_BASE_URL=https://genomeai.ru` |
| `scripts/rotate_admin_for_prod.py` | Создание нового admin + деактивация дефолтного `admin/admin` |

Не тронуто (CLAUDE.md §6 — оператор делает сам):
- `deploy/adult/compose.prod.yaml` — менять не нужно, монтирование `tls_certs:/etc/nginx/tls` уже описано в `compose.yaml`.
- `deploy/adult/secrets/*` — реальные секреты создаёт оператор.
- `deploy/adult/env/prod.env` — оператор копирует из `.example` и заполняет.

---

## 1. Переменные, которые нужно подставить

```bash
export LE_EMAIL="<your@email>"           # для Let's Encrypt уведомлений
export NEW_ADMIN_USERNAME="<owner>"      # любой непохожий-на-default
export NEW_ADMIN_PASSWORD="<strong-16+>" # сгенерируйте: openssl rand -base64 24
```

---

## 2. Шаги

### 2.1 DNS (15 минут — у регистратора domain'а)

В DNS-зоне `genomeai.ru` добавить A-записи:

```
genomeai.ru     A   91.229.105.152
www.genomeai.ru A   91.229.105.152
```

Подождать пропагации:

```bash
dig +short genomeai.ru @1.1.1.1
dig +short www.genomeai.ru @1.1.1.1
# должны вернуть 91.229.105.152
```

### 2.2 Firewall (1 минута)

```bash
sudo ufw allow 80/tcp     # для ACME http-01 + redirect
sudo ufw allow 443/tcp
sudo ufw reload
sudo ufw status
```

### 2.3 Остановить dev-серверы (важно — освободить :80 для certbot)

```bash
# next dev (если ещё бежит на :3000) — оставьте, он на 3000 и не мешает
# uvicorn на :8000 — оставьте, не мешает
# ВАЖНО: чтобы certbot --standalone мог зайти на :80
sudo ss -ltn | grep -E ":(80|443)"      # должно быть пусто
```

Если что-то слушает :80 — найдите процесс и остановите.

### 2.4 TLS-сертификат через Let's Encrypt (5 минут)

```bash
sudo apt-get update && sudo apt-get install -y certbot

sudo certbot certonly --standalone \
  --non-interactive --agree-tos \
  --email "$LE_EMAIL" \
  -d genomeai.ru -d www.genomeai.ru

# Результат:
# /etc/letsencrypt/live/genomeai.ru/fullchain.pem
# /etc/letsencrypt/live/genomeai.ru/privkey.pem
```

### 2.5 Сгенерировать недостающие секреты

В `deploy/adult/secrets/` уже есть 4 реальных файла. Создать недостающие:

```bash
cd deploy/adult/secrets

# Если нет:
test -f genomeai_web_secret || openssl rand -base64 64 | tr -d '\n' > genomeai_web_secret
test -f redis_password      || openssl rand -base64 32 | tr -d '\n' > redis_password

# Проверка набора (должны быть, БЕЗ .example):
ls | grep -v .example
# auth_refresh_hmac_key
# auth_signing_key
# genomeai_web_secret
# internal_service_token
# minio_root_password
# minio_root_user
# postgres_password
# postgres_runtime_dsn
# redis_password

# Права (по CLAUDE.md §7):
chmod 600 ./*
```

### 2.6 Создать env/prod.env из шаблона

```bash
cd /opt/genomeai/repo/deploy/adult
cp env/prod.env.example env/prod.env
# Проверьте GENOMEAI_WEB_BASE_URL=https://genomeai.ru
# Если своя ферма/тенант — добавить переменные сюда же
```

### 2.7 Положить cert'ы в `tls_certs` volume

`compose.yaml` уже монтирует named volume `tls_certs:/etc/nginx/tls`. Нужно положить туда LE-сертификаты:

```bash
cd /opt/genomeai/repo/deploy/adult
docker volume create adult_tls_certs 2>/dev/null || true

# Имя volume в compose — это <project>_tls_certs, по умолчанию project=adult.
# Проверьте реальное имя:
docker volume ls | grep tls

# Копируем cert'ы в volume:
docker run --rm \
  -v adult_tls_certs:/dst \
  -v /etc/letsencrypt/live/genomeai.ru:/src:ro \
  alpine sh -c "cp -L /src/fullchain.pem /src/privkey.pem /dst/ && chmod 644 /dst/*.pem"

# Проверка:
docker run --rm -v adult_tls_certs:/dst alpine ls -la /dst
```

### 2.8 Каталог под ACME-challenge для будущих renewals

```bash
sudo mkdir -p /var/www/acme
sudo chown www-data:www-data /var/www/acme || sudo chown root:root /var/www/acme
```

В `compose.yaml::reverse-proxy.volumes` уже есть `tls_certs:/etc/nginx/tls`. Для renewals нужен будет дополнительный bind-mount `/var/www/acme:/var/www/acme:rw` — но это уже после первого запуска (см. §3 ниже).

### 2.9 Поднять стек

```bash
cd /opt/genomeai/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml \
  --env-file env/prod.env up -d --build

# Проверьте статус:
docker compose ps
```

### 2.10 Применить миграции БД (если первый запуск)

```bash
docker compose -f compose.yaml -f compose.prod.yaml \
  --env-file env/prod.env exec backend-api \
  alembic upgrade head
```

### 2.11 Ротация admin-учётки

Сначала dry-run:

```bash
docker compose -f compose.yaml -f compose.prod.yaml \
  --env-file env/prod.env exec backend-api \
  python scripts/rotate_admin_for_prod.py \
    --new-username "$NEW_ADMIN_USERNAME" \
    --new-password "$NEW_ADMIN_PASSWORD" \
    --tenant-id default \
    --deactivate-default-admin \
    --dry-run
```

Потом боевой прогон (убрав `--dry-run`):

```bash
docker compose -f compose.yaml -f compose.prod.yaml \
  --env-file env/prod.env exec backend-api \
  python scripts/rotate_admin_for_prod.py \
    --new-username "$NEW_ADMIN_USERNAME" \
    --new-password "$NEW_ADMIN_PASSWORD" \
    --tenant-id default \
    --deactivate-default-admin
```

Verify:

```bash
# Новый admin должен работать:
curl -sX POST https://genomeai.ru/api/auth/login \
  -H "content-type: application/json" \
  -d "{\"username\":\"$NEW_ADMIN_USERNAME\",\"password\":\"$NEW_ADMIN_PASSWORD\"}" | jq .user.role

# Дефолтный admin/admin должен быть отключён (HTTP 401 или is_active=FALSE):
curl -sX POST https://genomeai.ru/api/auth/login \
  -H "content-type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

### 2.12 End-to-end проверки

```bash
# Health endpoints через reverse-proxy (TLS):
curl -fsS https://genomeai.ru/healthz
curl -fsS https://genomeai.ru/readyz

# Apex рендерит UI:
curl -sI https://genomeai.ru/ | head -5

# www → 301 → apex:
curl -sI https://www.genomeai.ru/ | head -5
# Должно быть: HTTP/2 301; Location: https://genomeai.ru/

# HTTP → 301 → HTTPS:
curl -sI http://genomeai.ru/ | head -5
# Должно быть: HTTP/1.1 301; Location: https://genomeai.ru/

# TLS rating — проверьте на https://www.ssllabs.com/ssltest/analyze.html?d=genomeai.ru
# Ожидаемый grade: A или A+ (TLSv1.2/1.3 + HSTS из security_headers.conf).
```

### 2.13 Browser-проверка

Откройте https://genomeai.ru — должен открыться экран логина. Войдите под `$NEW_ADMIN_USERNAME` / `$NEW_ADMIN_PASSWORD`. Перейдите на `/economics`, переключите 3 таба — должно совпасть с post-push smoke (см. `docs/iterations/T34-P2-1_economics_execution_proof.md`).

---

## 3. Auto-renewal Let's Encrypt (после первого успешного запуска)

LE-сертификат живёт 90 дней. Для авто-обновления:

### 3.1 Включить webroot-mode в nginx

Уже включено в новом `genomeai.conf` (location `^~ /.well-known/acme-challenge/` слушает на :80 → `/var/www/acme`).

### 3.2 Добавить bind-mount в reverse-proxy

В `deploy/adult/compose.prod.yaml` (или новый `compose.tls.yaml` override) добавьте к сервису `reverse-proxy`:

```yaml
volumes:
  - /var/www/acme:/var/www/acme:rw
```

(Это контрактное изменение — CLAUDE.md §6 запрещает мне делать без явного указания. После того как первый запуск пройдёт — попросите меня сделать override-файл.)

### 3.3 Cron на хосте

```bash
sudo crontab -e
```

Добавить:

```cron
0 3 * * 1  certbot renew --webroot -w /var/www/acme --quiet --deploy-hook "docker compose -f /opt/genomeai/repo/deploy/adult/compose.yaml -f /opt/genomeai/repo/deploy/adult/compose.prod.yaml --env-file /opt/genomeai/repo/deploy/adult/env/prod.env exec -T reverse-proxy nginx -s reload && docker run --rm -v adult_tls_certs:/dst -v /etc/letsencrypt/live/genomeai.ru:/src:ro alpine sh -c 'cp -L /src/fullchain.pem /src/privkey.pem /dst/'"
```

Каждый понедельник в 3 утра certbot проверит срок, обновит если меньше 30 дней, скопирует в volume и перезагрузит nginx.

---

## 4. Smoke-чек после деплоя

Сводный one-liner для оператора:

```bash
for url in healthz readyz; do
  curl -fsS -o /dev/null -w "%{http_code} https://genomeai.ru/$url\n" "https://genomeai.ru/$url"
done

# Логин:
TOKEN=$(curl -sX POST https://genomeai.ru/api/auth/login \
  -H "content-type: application/json" \
  -d "{\"username\":\"$NEW_ADMIN_USERNAME\",\"password\":\"$NEW_ADMIN_PASSWORD\"}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['tokens']['access_token'])")

# Экономика endpoint:
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "https://genomeai.ru/api/app/v1/economics/summary?data_version=dv_demo_farm_v1" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('schema=',d['schema']);print('warnings=',len(d['warnings']))"
```

Ожидаемое: `schema= genomeai.api.economics.summary.v1`, `warnings=6` (graceful degradation, без artifacts).

---

## 5. Что НЕ сделано в этом deploy

- **AI-features** (Claude API): без `OPENAI_API_KEY_FILE` или `ANTHROPIC_API_KEY_FILE` Copilot и Daily Briefing вернут 503/disabled. Добавляется отдельно когда понадобится.
- **Production data**: пустая БД после миграций. CSV-импорт через `/connections` либо `genomeai ingest` CLI — отдельная процедура.
- **Monitoring**: Prometheus стартует в compose, но Grafana/alerting не настроены — это `docs/operations_runbook.md`.

## 6. Rollback

```bash
cd /opt/genomeai/repo/deploy/adult
docker compose -f compose.yaml -f compose.prod.yaml --env-file env/prod.env down
# Состояние: домен возвращается к 503/timeout, БД сохранена в volumes
```

LE-cert никак не зависит от docker — он остаётся в `/etc/letsencrypt/`.
