#!/usr/bin/env bash
set -euo pipefail
python scripts/validate_t32_14_ui_verification_manuals.py
pytest -q tests/test_t32_14_ui_functional_verification_manuals.py
