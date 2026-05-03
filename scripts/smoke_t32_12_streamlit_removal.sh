#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
python scripts/validate_t32_12_streamlit_removal.py
pytest -q tests/test_t32_12_streamlit_removal_and_cleanup.py
