#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="${CI_ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts/_ci}"
PERF_REPORT_ROOT="${CI_PERF_REPORT_ROOT:-${ARTIFACTS_DIR}/performance_gates}"
PERF_PROFILE="${CI_PERF_PROFILE:-ci}"
mkdir -p "${ARTIFACTS_DIR}" "${PERF_REPORT_ROOT}"

PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" \
python -m genomeai.cli perf-gates \
  --project-root "${ROOT_DIR}" \
  --artifacts "${ROOT_DIR}/artifacts" \
  --golden "${ROOT_DIR}/golden" \
  --profile "${PERF_PROFILE}" \
  --report-root "${PERF_REPORT_ROOT}" | tee "${ARTIFACTS_DIR}/perf_gates.log"
