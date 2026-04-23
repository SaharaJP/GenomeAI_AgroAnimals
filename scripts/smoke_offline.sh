#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DV="dv_smoke_offline_$(date -u +%Y%m%d_%H%M%S)"

echo "[smoke_offline] data_version=$DV"

python -m genomeai smoke --out-version "$DV" --artifacts artifacts 

echo "[smoke_offline] OK"
