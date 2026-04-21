#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WEB_SMOKE_DIR="${1:-/tmp/t15_06_qc_refactor_web_smoke}"

TESTS=(
  tests/test_a2_qc.py
  tests/test_t0_04_qc2_engine.py
  tests/test_t4_01_health_qc_v2.py
  tests/test_dashboard_vet.py
  tests/test_t15_06_qc_core_unified.py
  tests/test_t15_06_alerts_qc2_layout.py
  tests/test_t15_06_qc2_path_resolution.py
  tests/test_t15_06_qc2_registration.py
  tests/test_t15_06_pack_decision_log_deterministic.py
  tests/web/test_alerts_v2.py
  tests/web/test_t12_02_auto_tasking.py
  tests/web/test_tasks_v1.py
)

echo "[T15-06] targeted pytest"
pytest -q "${TESTS[@]}"

echo "[T15-06] verify_refactor"
python -m genomeai verify_refactor --project-root . --golden golden

echo "[T15-06] smoke_offline"
bash scripts/smoke_offline.sh

echo "[T15-06] smoke_web -> $WEB_SMOKE_DIR"
bash scripts/smoke_web.sh "$WEB_SMOKE_DIR"

echo "T15_06_QC_REFACTOR_VERIFY_OK"
