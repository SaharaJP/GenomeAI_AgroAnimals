#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="${CI_ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts/_ci}"
PYTEST_LIST="${CI_PYTEST_LIST:-${ROOT_DIR}/ci/pytest_gate.txt}"
mkdir -p "${ARTIFACTS_DIR}"

mapfile -t TEST_ARGS < <(grep -Ev '^[[:space:]]*(#|$)' "${PYTEST_LIST}")
if [ ${#TEST_ARGS[@]} -eq 0 ]; then
  echo "CI pytest gate list is empty: ${PYTEST_LIST}" >&2
  exit 2
fi

pytest -q --junitxml "${ARTIFACTS_DIR}/pytest.junit.xml" "${TEST_ARGS[@]}" | tee "${ARTIFACTS_DIR}/pytest.log"
python scripts/report_warning_log.py "${ARTIFACTS_DIR}/pytest.log" "${ARTIFACTS_DIR}/pytest.warning_report.json"
PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python scripts/export_test_env_snapshot.py "${ARTIFACTS_DIR}/python_environment.json"
