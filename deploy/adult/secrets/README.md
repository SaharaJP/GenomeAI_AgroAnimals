# Runtime secrets directory baseline

Каталог содержит **примерные файлы секретов** для on-prem/stage/prod deployment.

## Правила

- реальные секреты **не коммитятся**;
- `.example` файлы используются как шаблоны;
- stage/prod env examples должны ссылаться на `/run/secrets/*` через `*_FILE`;
- этот каталог монтируется read-only в контейнеры как `/run/secrets`.

## Минимальный набор

- `genomeai_web_secret`
- `internal_service_token`
- `auth_signing_key`
- `auth_refresh_hmac_key`
- `postgres_password`
- `redis_password`
- `minio_root_password`
- `tls.crt` / `tls.key` предоставляются отдельно в `tls_certs` volume или эквивалентном secret mount.
