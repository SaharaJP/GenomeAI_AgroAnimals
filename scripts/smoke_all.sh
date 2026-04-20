#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/smoke_offline.sh
./scripts/smoke_web.sh
./scripts/backup_restore_check.sh

echo "[smoke_all] OK"
