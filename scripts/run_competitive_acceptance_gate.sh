#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="${CI_ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts/_ci}"
REPORT_ROOT="${CI_COMPETITIVE_ACCEPTANCE_REPORT_ROOT:-${ARTIFACTS_DIR}/competitive_acceptance}"
PROFILE="${CI_COMPETITIVE_ACCEPTANCE_PROFILE:-legacy_replacement_ci}"
mkdir -p "${ARTIFACTS_DIR}" "${REPORT_ROOT}"

PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python scripts/smoke_t30_01_competitive_acceptance_set.py \
  --project-root "${ROOT_DIR}" \
  --artifacts "${ROOT_DIR}/artifacts" \
  --profile "${PROFILE}" \
  --report-root "${REPORT_ROOT}" | tee "${ARTIFACTS_DIR}/competitive_acceptance_gate.log"
