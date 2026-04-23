#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src:. python scripts/smoke_t31_05_commercial_readiness_gate.py   --project-root .   --artifacts-root artifacts   --report-root artifacts/_ci/commercial_readiness_v1
