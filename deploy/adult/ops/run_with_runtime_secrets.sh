#!/bin/sh
set -eu

load_secret() {
  var_name="$1"
  file_var_name="${var_name}_FILE"
  eval "current_value=\${$var_name-}"
  eval "file_value=\${$file_var_name-}"

  if [ -n "${current_value:-}" ] && [ -n "${file_value:-}" ]; then
    echo "Both ${var_name} and ${file_var_name} are set; only one is allowed" >&2
    exit 1
  fi

  if [ -n "${file_value:-}" ]; then
    if [ ! -f "$file_value" ]; then
      echo "Secret file for ${var_name} not found: $file_value" >&2
      exit 1
    fi
    export "$var_name=$(tr -d '\r\n' < "$file_value")"
  fi
}

for secret_name in \
  GENOMEAI_WEB_SECRET \
  GENOMEAI_INTERNAL_SERVICE_TOKEN \
  GENOMEAI_AUTH_SIGNING_KEY \
  GENOMEAI_AUTH_REFRESH_HMAC_KEY \
  POSTGRES_PASSWORD \
  REDIS_PASSWORD \
  MINIO_ROOT_USER \
  MINIO_ROOT_PASSWORD
 do
  load_secret "$secret_name"
 done

exec "$@"
