# T32-10A — Production security / IAM / secrets / network baseline

## Что фиксирует этот шаг

Этот шаг добавляет к `deploy/adult/` **формальный security/IAM baseline** для on-prem / enterprise deployment contour.

Он опирается на уже реализованную unified auth/session model (`/api/app/v1/auth/*`) и связывает её с deployment-level controls:

- token policy;
- refresh / revoke discipline;
- secrets handling через `*_FILE` и `/run/secrets`;
- TLS / reverse-proxy security headers baseline;
- network boundaries между edge / app / data / ops;
- service-to-service trust baseline;
- audit-sensitive operations;
- support / incident / release discipline.

Шаг **не обещает enterprise certification** или внешний IAM/SSO из коробки. Он фиксирует **проверяемый production baseline**, который команда может использовать как минимальную взрослую базу для on-prem deployments.

## Unified auth / IAM baseline

Серверная модель auth остаётся единой для web и Android:

- access token;
- refresh token;
- session list;
- revoke single session;
- revoke by logout / logout-all.

Канонический boundary уже определён в `/api/app/v1/auth/*`, а deployment baseline закрепляет его operational policy.

### Token policy

Зафиксирована checked-in policy:

- `configs/security/production_iam_token_policy_v1.json`

Базовые значения по умолчанию:

- access token TTL: **900 сек**;
- refresh token TTL: **30 дней** (`2592000` сек);
- refresh rotation: **включена**;
- revoke on logout: **обязательно**;
- revoke on session revoke: **обязательно**;
- refresh reuse без server-side session lineage **не допускается**.

### Audit-sensitive операции

Audit-sensitive операции, которые должны логироваться и подчиняться incident/release discipline:

- login / refresh / logout / revoke session;
- rotation secrets;
- backup / restore;
- report governance actions;
- support / pilot / readiness actions;
- deployment profile changes;
- manual emergency access / break-glass actions (если вводятся отдельно).

## Secrets handling baseline

### Принцип

Секреты **не должны** жить только в README или быть зашиты в compose напрямую для stage/prod. Используется pattern:

- env var `FOO` — допустим для dev/test;
- env var `FOO_FILE` — обязателен для stage/prod, когда это возможно;
- runtime secrets directory: `/run/secrets`.

### Что зафиксировано

- `deploy/adult/secrets/README.md`
- примеры файлов секретов в `deploy/adult/secrets/*.example`
- stage/prod env examples используют `*_FILE` pattern для ключевых секретов

Ключевые секреты baseline:

- `GENOMEAI_WEB_SECRET_FILE`
- `GENOMEAI_INTERNAL_SERVICE_TOKEN_FILE`
- `GENOMEAI_AUTH_SIGNING_KEY_FILE`
- `GENOMEAI_AUTH_REFRESH_HMAC_KEY_FILE`
- `POSTGRES_PASSWORD_FILE`
- `REDIS_PASSWORD_FILE`
- `MINIO_ROOT_PASSWORD_FILE`
- `MINIO_ROOT_USER_FILE` (опционально)

### Runtime loading

Python services запускаются через `deploy/adult/ops/run_with_runtime_secrets.sh`, который:

- читает `*_FILE` значения;
- запрещает одновременную установку `FOO` и `FOO_FILE`;
- валит старт, если указан file path, но файла нет;
- экспортирует секреты в процесс **только на runtime**.

## TLS / ingress baseline

Зафиксированы:

- `deploy/adult/security/tls_server.conf.example`
- `deploy/adult/security/security_headers.conf`

### Что считается baseline

- reverse proxy публикует HTTP/HTTPS ingress;
- для TLS используются внешне предоставленные сертификаты (`/etc/nginx/tls/tls.crt`, `/etc/nginx/tls/tls.key`);
- security headers включены на ingress;
- `server_tokens off` и request-id forwarding обязательны;
- HSTS разрешён только в TLS server block.

Шаг **не утверждает**, что сертификаты автоматически выпускаются или ротируются этим же репозиторием. Для on-prem это обычно внешний PKI / внутренний CA / корпоративный cert lifecycle.

## Network boundaries

В `deploy/adult/compose.yaml` сервисы разведены по сетям:

- `edge_net` — ingress/public edge;
- `app_net` — frontend ↔ backend application traffic;
- `data_net` — postgres / redis / artifact storage;
- `ops_net` — prometheus / internal ops / future diagnostics.

### Правила baseline

- reverse proxy доступен на `edge_net`;
- database/cache/object storage **не публикуются наружу**;
- worker/scheduler не сидят в `edge_net`;
- frontend не ходит напрямую в `data_net`;
- prometheus сидит в `ops_net`, а не в public edge.

Дополнительно добавлены примеры:

- `deploy/adult/k8s/networkpolicy.example.yaml`
- `configs/security/service_trust_policy_v1.json`

## Service-to-service auth baseline

Service-to-service auth на этом шаге фиксируется как **shared internal service token baseline**, а не как полный service mesh.

Базовый механизм:

- shared secret: `GENOMEAI_INTERNAL_SERVICE_TOKEN` / `GENOMEAI_INTERNAL_SERVICE_TOKEN_FILE`;
- policy manifest: `configs/security/service_trust_policy_v1.json`;
- token предназначен для внутренних ops/integration flows, а не для пользовательского UI access.

Это baseline, а не full zero-trust mesh. Но он убирает хаотичные implicit assumptions и даёт единый trust anchor для внутренних сервисов.

## Security checklist для on-prem / enterprise baseline

Зафиксирован checked-in checklist:

- `configs/security/onprem_security_checklist_v1.json`

Минимальные обязательные пункты перед stage/prod rollout:

1. Все default secrets заменены.
2. Stage/prod используют `*_FILE` pattern.
3. TLS cert/key присутствуют и примонтированы.
4. Redis защищён паролем.
5. PostgreSQL пароль подаётся через file secret.
6. Object storage root password заменён.
7. Public ports открыты только у ingress.
8. Backup/restore протестированы в отдельном окне.
9. Session revoke / logout / refresh flows проверены.
10. Incident procedure и release approval задокументированы.

## Связь с support / incident / release discipline

Security baseline связан с operational discipline:

- при incident response допускается session revoke / secret rotation / access block;
- support-операции с повышенной чувствительностью должны оставаться audit-visible;
- релиз не считается production-ready, если не пройдены checklist + security validator.

Это связывает T32-10A с support/incident/release discipline и убирает сценарий «security только на словах».

## Что intentionally не обещается

Этот шаг **не утверждает**:

- что уже реализованы SSO / IdP / SCIM / MFA;
- что service-to-service auth уже равен enterprise service mesh;
- что есть внешняя сертификация hardening;
- что deployment автоматически удовлетворяет внутренним policy любой конкретной корпорации.

Но шаг даёт **формальный, проверяемый и runnable baseline**, на который можно опираться дальше.
