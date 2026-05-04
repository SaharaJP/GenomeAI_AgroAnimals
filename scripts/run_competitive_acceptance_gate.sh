#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="${CI_ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts/_ci}"
REPORT_ROOT="${CI_COMPETITIVE_ACCEPTANCE_REPORT_ROOT:-${ARTIFACTS_DIR}/competitive_acceptance}"
PROFILE="${CI_COMPETITIVE_ACCEPTANCE_PROFILE:-legacy_replacement_ci}"
mkdir -p "${ARTIFACTS_DIR}" "${REPORT_ROOT}"

# Load .env.ai for Postgres DSN — migration smoke scripts require GENOMEAI_RUNTIME_POSTGRES_DSN
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.ai}"
if [[ -f "$ENV_FILE" ]]; then
  set -a && source "$ENV_FILE" && set +a
fi
export GENOMEAI_RUNTIME_POSTGRES_DSN="${GENOMEAI_RUNTIME_POSTGRES_DSN:-${GENOMEAI_TEST_DSN:-}}"

PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python scripts/smoke_t30_01_competitive_acceptance_set.py \
  --project-root "${ROOT_DIR}" \
  --artifacts "${ROOT_DIR}/artifacts" \
  --profile "${PROFILE}" \
  --report-root "${REPORT_ROOT}" | tee "${ARTIFACTS_DIR}/competitive_acceptance_gate.log"
