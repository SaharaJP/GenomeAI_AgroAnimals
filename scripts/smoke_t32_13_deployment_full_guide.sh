#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/validate_t32_13_deployment_full_guide.py
bash -n deploy/adult/ops/post_deploy_smoke.sh
bash -n deploy/adult/ops/collect_support_bundle.sh
python -m pytest -q tests/test_t32_13_deployment_full_guide.py
