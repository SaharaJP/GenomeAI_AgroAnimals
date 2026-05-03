#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${GENOMEAI_APP_ROOT:-$HOME/.genomeai_agroanimals}"
LOCAL_BIN="$HOME/.local/bin"
DESKTOP_FILE="$HOME/.local/share/applications/genomeai-agroanimals.desktop"
USER_DESKTOP="$HOME/Desktop"

echo "[GenomeAI] removing $APP_ROOT"

rm -f "$LOCAL_BIN/genomeai-agroanimals" || true
rm -f "$DESKTOP_FILE" || true
rm -f "$USER_DESKTOP/GenomeAI AgroAnimals.desktop" || true
rm -f "$USER_DESKTOP/GenomeAI AgroAnimals.command" || true
rm -rf "$APP_ROOT" || true

echo "OK: uninstalled"