#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "No python interpreter found (expected python3 or python)" >&2
  exit 1
fi
PYTHONPATH="$ROOT/src:$ROOT" "$PYTHON_BIN" "$ROOT/scripts/smoke_t30_03_demo_farm.py" \
  --dataset-dir "$ROOT/data/demo/demo_farm_v1" \
  --report-root "$ROOT/artifacts/_ci/demo_farm_v1"
