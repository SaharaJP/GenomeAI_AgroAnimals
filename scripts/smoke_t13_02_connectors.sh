#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cleanup_generated_configs() {
  rm -f configs/connectors/partial_retry_*.yaml \
    configs/connectors/detail_retry_*.yaml \
    configs/connectors/auto_retry_*.yaml \
    configs/connectors/ui_retry_policy_*.yaml \
    configs/connectors/guardrail_retry_*.yaml \
    configs/connectors/recovery_cancel_*.yaml \
    configs/connectors/upload_flow_*.yaml \
    configs/connectors/detail_flow_*.yaml \
    configs/connectors/ui_editor_*.yaml \
    configs/connectors/preview_*.yaml \
    configs/connectors/force_slot_*.yaml \
    configs/connectors/binding_delta_*.yaml \
    configs/connectors/outputs_preview_*.yaml || true
}

echo "[T13-02] pre-cleanup stale connector configs"
cleanup_generated_configs
python -m genomeai connectors cleanup --configs-dir configs/connectors

echo "[T13-02] validate demo connector"
python -m genomeai connectors validate --config configs/connectors/file_demo.yaml --project-root .

echo "[T13-02] schedule tick"
python -m genomeai connectors schedule --configs-dir configs/connectors --at 2026-03-07T06:00:00+00:00 || true

echo "[T13-02] connector-focused tests"
pytest -q tests/test_t13_02_connectors_step1.py \
  tests/test_t13_02_connectors_step14_final_cleanup.py \
  tests/web/test_t13_02_connectors_step10_partial_retry.py \
  tests/web/test_t13_02_connectors_step11_recovery_queue.py \
  tests/web/test_t13_02_connectors_step12_retry_policy_guardrails.py \
  tests/web/test_t13_02_connectors_step13_recovery_cancel.py

echo "[T13-02] post-cleanup generated test configs"
cleanup_generated_configs
python -m genomeai connectors cleanup --configs-dir configs/connectors
