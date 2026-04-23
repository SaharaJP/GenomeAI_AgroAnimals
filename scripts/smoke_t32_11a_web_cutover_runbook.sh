#!/usr/bin/env bash
set -euo pipefail

python scripts/validate_t32_11a_web_cutover_runbook.py --write
python scripts/validate_t32_11a_web_cutover_runbook.py --assert-current
pytest -q tests/test_t32_11a_web_cutover_runbook.py

echo "web cutover / coexistence / rollback runbook smoke passed"
