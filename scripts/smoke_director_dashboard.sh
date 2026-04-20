#!/usr/bin/env bash
set -euo pipefail

ARTIFACTS=${ARTIFACTS:-artifacts}
DV=${DV:-dv_demo_dash}
ASOF=${ASOF:-2025-01-05}

echo "[smoke_director_dashboard] compute KPI"
genomeai kpi --data-version "$DV" --asof-date "$ASOF" --input-dir data/fixtures/target_v2 --artifacts "$ARTIFACTS"

echo "[smoke_director_dashboard] export director summary snapshot"
genomeai dashboard --data-version "$DV" --asof-date "$ASOF" --artifacts "$ARTIFACTS" --kpi-run-id "" --input-dir data/fixtures/target_v2

echo "OK"
