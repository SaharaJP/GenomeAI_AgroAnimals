#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="${CI_ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts/_ci}"
REPORT_ROOT="${CI_OPERATIONAL_REPORT_ROOT:-${ARTIFACTS_DIR}/operational_rollout_gates}"
WORKDIR_ROOT="${CI_OPERATIONAL_WORKDIR:-${ROOT_DIR}/_tmp/ci_operational_rollout}"
PROFILE="${CI_OPERATIONAL_PROFILE:-enterprise_ci}"
mkdir -p "${ARTIFACTS_DIR}" "${REPORT_ROOT}" "${WORKDIR_ROOT}"

PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python scripts/smoke_t28_05_operational_rollout_gates.py   --project-root "${ROOT_DIR}"   --artifacts "${ROOT_DIR}/artifacts"   --profile "${PROFILE}"   --report-root "${REPORT_ROOT}"   --workdir "${WORKDIR_ROOT}" | tee "${ARTIFACTS_DIR}/operational_rollout_gate.log"
