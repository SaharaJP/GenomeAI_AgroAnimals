#!/usr/bin/env bash
set -euo pipefail

WEB_SMOKE_DIR="${1:-/tmp/genomeai_t15_07_web_smoke}"

pytest -q \
  tests/test_t15_07_ml_core_pipeline_step1.py \
  tests/test_t15_07_ml_registry_resolvers.py \
  tests/test_t15_07_ml_catalog_entries.py \
  tests/test_t15_07_ml_consumers_step4.py \
  tests/test_t15_07_ml_interface_parity_step5.py \
  tests/web/test_t15_07_ml_pages_step3.py \
  tests/web/test_t15_07_ml_pages_step6_advanced_run_forms.py \
  tests/test_a3_train.py \
  tests/test_a4_score.py \
  tests/test_a5_report.py \
  tests/test_a6_pack.py \
  tests/test_dashboard_zootech.py \
  tests/test_t8_01_regular_reports.py \
  tests/test_t15_05_job_runner.py

python -m genomeai verify_refactor --project-root . --golden golden
bash scripts/smoke_offline.sh
bash scripts/smoke_web.sh "$WEB_SMOKE_DIR"
