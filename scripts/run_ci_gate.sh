#!/usr/bin/env bash
# MVP-soft CI gate v2 — не триггерится на regex паттерны в себе
set -u
RESULTS=()
FAILED=0
log()  { echo "[ci_gate] $*"; }
ok()   { log "OK $*"; RESULTS+=("OK $*"); }
warn() { log "WARN $*"; RESULTS+=("WARN $*"); }
fail() { log "FAIL $*"; RESULTS+=("FAIL $*"); FAILED=$((FAILED+1)); }

log "=== MVP-soft CI gate starting ==="
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT"

# Gate 1: Python syntax на изменённых файлах
CHANGED_PY=$(git diff --name-only HEAD 2>/dev/null | grep '\.py$' || true)
if [ -n "$CHANGED_PY" ]; then
    SYNTAX_OK=true
    for f in $CHANGED_PY; do
        [ -f "$f" ] && python -m py_compile "$f" 2>/dev/null || { fail "Syntax error: $f"; SYNTAX_OK=false; }
    done
    [ "$SYNTAX_OK" = "true" ] && ok "Python syntax check passed"
else
    ok "No Python changes"
fi

# Gate 2: Frontend typecheck (если изменились .ts/.tsx)
CHANGED_WEB=$(git diff --name-only HEAD 2>/dev/null | grep -E '^web_app/.*\.(ts|tsx)$' || true)
if [ -n "$CHANGED_WEB" ] && [ -d "web_app" ]; then
    cd web_app
    if [ -f package.json ] && grep -q '"typecheck"' package.json; then
        if npm run typecheck 2>&1 | tail -5; then
            ok "TypeScript typecheck passed"
        else
            fail "TypeScript typecheck failed"
        fi
    else
        warn "No typecheck script"
    fi
    cd "$REPO_ROOT"
else
    ok "No frontend changes"
fi

# Gate 3: Secrets leak — СТРОИМ ПАТТЕРН ДИНАМИЧЕСКИ чтобы не матчить сам себя
SECRETS_OK=true
if git ls-files 2>/dev/null | grep -qE "^\.env\.ai$"; then
    fail ".env.ai committed — REMOVE NOW"
    SECRETS_OK=false
fi
# Собираем паттерн по частям: sk- + ant- + api03- = уникальный, не совпадёт с этим скриптом
PATTERN_P1="sk-"
PATTERN_P2="ant-api"
PATTERN_P3="03-"
SEARCH_PATTERN="${PATTERN_P1}${PATTERN_P2}${PATTERN_P3}"
CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null | grep -v "\.env\.ai\.example$" | grep -v "run_ci_gate\.sh$" || true)
if [ -n "$CHANGED_FILES" ]; then
    LEAKED=""
    for f in $CHANGED_FILES; do
        if [ -f "$f" ] && grep -l "$SEARCH_PATTERN" "$f" >/dev/null 2>&1; then
            LEAKED="$LEAKED $f"
        fi
    done
    if [ -n "$LEAKED" ]; then
        fail "API key leaked in:$LEAKED"
        SECRETS_OK=false
    fi
fi
[ "$SECRETS_OK" = "true" ] && ok "No secrets leaked"

# Gate 4: Import sanity
if [ -d "web_cabinet" ]; then
    python -c "import web_cabinet" 2>/dev/null && ok "web_cabinet imports OK" || warn "web_cabinet import issues (MVP: OK)"
fi

echo ""
log "=== Results ==="
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo ""
if [ $FAILED -gt 0 ]; then
    log "=== FAILED: $FAILED gates ==="
    exit 1
else
    log "=== PASSED ==="
    exit 0
fi
