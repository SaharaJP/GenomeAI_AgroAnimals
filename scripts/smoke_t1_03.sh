#!/usr/bin/env bash
set -euo pipefail

# Smoke for T1-03: build synthetic pipeline (A1..A6) + export zootech dashboard snapshot.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ARTIFACTS_ROOT="${ARTIFACTS_ROOT:-${ROOT_DIR}/artifacts}"
CONTRACTS_DIR="${CONTRACTS_DIR:-${ROOT_DIR}/configs/contracts}"
DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data/examples}"
MAPPINGS_DIR="${MAPPINGS_DIR:-${ROOT_DIR}/configs/mappings}"

export ARTIFACTS_ROOT CONTRACTS_DIR DATA_DIR MAPPINGS_DIR

python3 - <<'PY'
import json
import os
from pathlib import Path

from genomeai.smoke import run_smoke
from genomeai.dashboard_zootech import export_zootech_dashboard, ZootechDashboardInputs

artifacts_root = Path(os.environ.get("ARTIFACTS_ROOT", "artifacts"))
contracts_dir = Path(os.environ.get("CONTRACTS_DIR", "configs/contracts"))
data_dir = Path(os.environ.get("DATA_DIR", "data/examples"))
mappings_dir = Path(os.environ.get("MAPPINGS_DIR", "configs/mappings"))

res = run_smoke(
    artifacts_root=artifacts_root,
    contracts_dir=contracts_dir,
    data_dir=data_dir,
    mappings_dir=mappings_dir,
)

if not res.get("ok"):
    raise SystemExit(json.dumps(res, ensure_ascii=False, indent=2))

summary = res["summary"]
dv = summary["data_version"]
sr = summary["scoring_run"]

run_root = export_zootech_dashboard(
    inputs=ZootechDashboardInputs(data_version=dv, artifacts_dir=artifacts_root, scoring_run=sr),
    run_id="dash_smoke_zootech",
    user="smoke",
)

print(json.dumps({"ok": True, "data_version": dv, "scoring_run": sr, "zootech_dashboard_run": str(run_root)}, ensure_ascii=False, indent=2))
PY

echo "[OK] T1-03 smoke completed"
