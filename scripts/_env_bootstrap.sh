#!/usr/bin/env bash
# scripts/_env_bootstrap.sh — общий загрузчик окружения для gate-скриптов.
# Источник: source "$(dirname "${BASH_SOURCE[0]}")/_env_bootstrap.sh"
#
# Что делает:
#   1. Загружает .env.ai (если есть) — источник GENOMEAI_TEST_DSN и прочих ключей.
#   2. Проставляет GENOMEAI_RUNTIME_POSTGRES_DSN из GENOMEAI_TEST_DSN если не задан явно.
#
# Это safe-to-source: не меняет DSN если уже задан через CI env или оператором.

_BOOTSTRAP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ENV_FILE="${ENV_FILE:-${_BOOTSTRAP_ROOT}/.env.ai}"

if [[ -f "$_ENV_FILE" ]]; then
  set -a && source "$_ENV_FILE" && set +a
fi

export GENOMEAI_RUNTIME_POSTGRES_DSN="${GENOMEAI_RUNTIME_POSTGRES_DSN:-${GENOMEAI_TEST_DSN:-}}"

unset _BOOTSTRAP_ROOT _ENV_FILE
