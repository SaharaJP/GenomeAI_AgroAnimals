#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python scripts/validate_t32_10_server_deployment.py >/dev/null
python scripts/validate_t32_10a_production_security.py
