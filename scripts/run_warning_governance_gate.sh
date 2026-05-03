#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="${CI_ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts/_ci}"
PYTEST_LOG="${CI_PYTEST_LOG:-${ARTIFACTS_DIR}/pytest.log}"
WEB_SMOKE_LOG="${CI_WEB_SMOKE_LOG:-${ARTIFACTS_DIR}/web_smoke.log}"
VERIFY_LOG="${CI_VERIFY_LOG:-${ARTIFACTS_DIR}/verify_refactor.log}"
REPORT_JSON="${CI_WARNING_REPORT_JSON:-${ARTIFACTS_DIR}/warning_governance_report.json}"
REPORT_MD="${CI_WARNING_REPORT_MD:-${ARTIFACTS_DIR}/warning_governance_report.md}"

mkdir -p "${ARTIFACTS_DIR}"
PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" \
  python "${ROOT_DIR}/scripts/check_warning_governance.py" \
    --pytest-log "${PYTEST_LOG}" \
    --web-smoke-log "${WEB_SMOKE_LOG}" \
    --verify-log "${VERIFY_LOG}" \
    --output-json "${REPORT_JSON}" \
    --output-md "${REPORT_MD}"
