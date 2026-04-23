#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src:. python scripts/smoke_t31_01_pilot_framework.py --project-root . --report-root artifacts/_ci/pilot_framework_v1
