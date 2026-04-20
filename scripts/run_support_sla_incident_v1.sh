#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src:. python scripts/smoke_t31_03_support_sla_incident_model.py \
  --project-root . \
  --artifacts-dir artifacts \
  --report-root artifacts/_ci/support_sla_incident_v1 \
  --web-storage-dir web_cabinet/storage
