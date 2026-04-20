#!/usr/bin/env bash
set -euo pipefail

# GenomeAI AgroAnimals installer (Linux/macOS)
# Установка в пользовательский каталог (без sudo): ~/.genomeai_agroanimals

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_ROOT="${GENOMEAI_APP_ROOT:-$HOME/.genomeai_agroanimals}"
VENV_DIR="$APP_ROOT/venv"
BIN_DIR="$APP_ROOT/bin"
LOCAL_BIN="$HOME/.local/bin"

PYTHON_BIN="${GENOMEAI_PYTHON:-python3}"

echo "[GenomeAI] repo_root=$REPO_ROOT"
echo "[GenomeAI] app_root=$APP_ROOT"

mkdir -p "$APP_ROOT" "$BIN_DIR" "$LOCAL_BIN"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.11+ and retry." >&2
  exit 2
fi

"$PYTHON_BIN" -c "import sys; print(sys.version)" >/dev/null

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install -U pip setuptools wheel >/dev/null

# Install editable from repo with UI extras.
"$VENV_DIR/bin/pip" install -e "$REPO_ROOT[ui]" >/dev/null

# Launcher wrapper (stable path)
cat >"$BIN_DIR/genomeai-agroanimals" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${GENOMEAI_APP_ROOT:-$HOME/.genomeai_agroanimals}"
exec "$APP_ROOT/venv/bin/genomeai-agroanimals" "$@"
EOF
chmod +x "$BIN_DIR/genomeai-agroanimals"

# Symlink into ~/.local/bin for удобного запуска
ln -sf "$BIN_DIR/genomeai-agroanimals" "$LOCAL_BIN/genomeai-agroanimals"

# Desktop entry (best-effort)
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat >"$DESKTOP_DIR/genomeai-agroanimals.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GenomeAI AgroAnimals
Comment=GenomeAI AgroAnimals (local cabinet)
Exec=$LOCAL_BIN/genomeai-agroanimals --open-browser
Terminal=false
Categories=Office;Science;
EOF

# Desktop shortcut (Linux): copy .desktop to ~/Desktop if it exists
if [ "$(uname -s)" = "Linux" ]; then
  USER_DESKTOP="$HOME/Desktop"
  if [ -d "$USER_DESKTOP" ]; then
    cp -f "$DESKTOP_DIR/genomeai-agroanimals.desktop" "$USER_DESKTOP/GenomeAI AgroAnimals.desktop" || true
    chmod +x "$USER_DESKTOP/GenomeAI AgroAnimals.desktop" || true
  fi
fi

# macOS: create clickable .command on Desktop (best-effort)
if [ "$(uname -s)" = "Darwin" ]; then
  USER_DESKTOP="$HOME/Desktop"
  if [ -d "$USER_DESKTOP" ]; then
    CMD_FILE="$USER_DESKTOP/GenomeAI AgroAnimals.command"
    cat >"$CMD_FILE" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$LOCAL_BIN/genomeai-agroanimals" --open-browser
EOF
    chmod +x "$CMD_FILE" || true
  fi
fi

echo "OK: installed"
echo "Run: genomeai-agroanimals --open-browser"
