#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_ROOT="${1:-$ROOT_DIR/artifacts/_ci/customer_upgrade_v1}"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
python "$ROOT_DIR/scripts/smoke_t31_04_customer_upgrade_discipline.py" \
  --project-root "$ROOT_DIR" \
  --report-root "$REPORT_ROOT"
