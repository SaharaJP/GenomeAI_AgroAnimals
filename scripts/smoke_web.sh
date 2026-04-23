#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WORKDIR="${1:-}"
if [[ -z "$WORKDIR" ]]; then
  WORKDIR="$ROOT_DIR/runtime/web_smoke"
fi

echo "[smoke_web] workdir=$WORKDIR"
python -m web_cabinet.smoke --workdir "$WORKDIR" --clean

echo "[smoke_web] OK"
