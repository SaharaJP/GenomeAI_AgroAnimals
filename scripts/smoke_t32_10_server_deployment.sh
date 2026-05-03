#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/validate_t32_10_server_deployment.py
