#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
python scripts/validate_t32_12a_streamlit_legacy_cleanup.py
pytest -q tests/test_t32_12a_streamlit_legacy_cleanup_gate.py
