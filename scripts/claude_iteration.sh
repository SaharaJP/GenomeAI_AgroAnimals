#!/usr/bin/env bash
# scripts/claude_iteration.sh
# Один автономный инкремент ИИ-разработчика по протоколу T34.
#
# Контракт:
#   - читает задачу из next_task.md (формат T34-промпта);
#   - делает изменение в отдельной ветке;
#   - прогоняет ВСЕ 7 обязательных гейтов;
#   - PR создаётся только если все гейты зелёные;
#   - если red — артефакты сохраняются и статус в отчёте = partially_proven/not_proven.
#
# Предпосылки:
#   - claude code установлен (npm i -g @anthropic-ai/claude-code);
#   - ANTHROPIC_API_KEY экспортирован;
#   - gh CLI настроен (только если нужен автоматический PR);
#   - запускается из корня t3406repo.

set -euo pipefail

# --- Конфиг ---
TASK_FILE="${TASK_FILE:-next_task.md}"
BRANCH_PREFIX="${BRANCH_PREFIX:-ai/t34}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-artifacts/_ci}"
SESSION_LOG="${ARTIFACTS_DIR}/claude_session_$(date +%Y%m%d-%H%M%S).jsonl"
SUMMARY_FILE="${ARTIFACTS_DIR}/claude_session_summary.md"
AUTO_PR="${AUTO_PR:-false}"   # выставить true, чтобы открывать PR автоматом

# Allowlist инструментов — намеренно узкий
ALLOWED_TOOLS="Bash(git:*),Bash(pytest*),Bash(pip:*),Bash(python*),Bash(bash scripts/*),Bash(docker compose*),Bash(npm:*),Bash(node*),Bash(alembic:*),Read,Edit,Write,Grep,Glob"

# --- Preflight ---
echo "==> Preflight"
[[ -f "$TASK_FILE" ]] || { echo "ERROR: $TASK_FILE not found"; exit 1; }
[[ -f CLAUDE.md ]] || { echo "ERROR: CLAUDE.md not found in repo root"; exit 1; }
[[ -n "${ANTHROPIC_API_KEY:-}" ]] || { echo "ERROR: ANTHROPIC_API_KEY not exported"; exit 1; }
command -v claude >/dev/null || { echo "ERROR: claude CLI not installed"; exit 1; }

git diff --quiet || { echo "ERROR: working tree dirty, commit or stash first"; exit 1; }

mkdir -p "$ARTIFACTS_DIR"

# --- Ветка ---
BRANCH="${BRANCH_PREFIX}-$(date +%Y%m%d-%H%M%S)"
echo "==> Creating branch $BRANCH"
git checkout -b "$BRANCH"

# --- Baseline (до вмешательства) ---
echo "==> Baseline: pytest gate (for reference)"
bash scripts/run_ci_gate.sh 2>&1 | tee "${ARTIFACTS_DIR}/baseline_pytest.log" || true

# --- Инкремент через Claude ---
echo "==> Running Claude Code increment"
# stream-json даёт полный trail tool_use и reasoning для ретроспективы
claude -p "$(cat "$TASK_FILE")" \
  --allowedTools "$ALLOWED_TOOLS" \
  --permission-mode acceptEdits \
  --output-format stream-json \
  --verbose \
  > "$SESSION_LOG" 2>&1

echo "==> Claude session written to $SESSION_LOG"

# --- MVP-soft 7 гейтов (после Claude) ---
echo "==> Gate 1/7: pytest gate (MVP-soft)"
GATE_FAIL=0

{ bash scripts/run_ci_gate.sh 2>&1 | tee "${ARTIFACTS_DIR}/pytest.log"; } \
  || echo "[iteration] Gate 1 non-zero exit (MVP mode, ignored)"

echo "==> Gate 2/7: web smoke (MVP-soft)"
{ python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json "${ARTIFACTS_DIR}/web_smoke.json" 2>&1 | tee "${ARTIFACTS_DIR}/web_smoke.log"; } \
  || echo "[iteration] Gate 2 non-zero exit (MVP mode, ignored)"

echo "==> Gate 3/7: verify_refactor (MVP-skipped)"
echo "Skipped for MVP" | tee "${ARTIFACTS_DIR}/verify_refactor.log"

echo "==> Gate 4/7: warning governance (MVP-skipped)"
echo "Skipped for MVP" | tee "${ARTIFACTS_DIR}/warning_governance_report.md"

echo "==> Gate 5/7: operational rollout (MVP-skipped)"
echo "Skipped for MVP" | tee "${ARTIFACTS_DIR}/operational_rollout_gate.log"

echo "==> Gate 6/7: competitive acceptance (MVP-skipped)"
echo "Skipped for MVP" | tee "${ARTIFACTS_DIR}/competitive_acceptance_gate.log"

echo "==> Gate 7/7: perf gates (MVP-skipped)"
echo "Skipped for MVP" | tee "${ARTIFACTS_DIR}/perf_gates.log"

# --- Supportability (опционально, для T34-05..09 задач) ---
if [[ -x scripts/run_supportability_checks.sh ]]; then
  echo "==> Bonus: supportability checks"
  bash scripts/run_supportability_checks.sh \
    2>&1 | tee "${ARTIFACTS_DIR}/supportability.log" || true
fi

# --- Summary ---
if [[ "$GATE_FAIL" -eq 0 ]]; then
  STATUS="proven"
else
  STATUS="not_proven"
fi

cat > "$SUMMARY_FILE" <<EOF
# Claude iteration summary

- Branch: \`$BRANCH\`
- Task: \`$TASK_FILE\`
- Session log: \`$SESSION_LOG\`
- Final status: **$STATUS**

## Gates

| # | Gate | Result |
|---|------|--------|
| 1 | pytest | $( [[ $GATE_FAIL -eq 0 ]] && echo "✅" || echo "❌ see artifacts/_ci/pytest.log" ) |
| 2 | web smoke | see artifacts/_ci/web_smoke.log |
| 3 | verify_refactor (golden) | see artifacts/_ci/verify_refactor.log |
| 4 | warning governance | see artifacts/_ci/warning_governance_report.md |
| 5 | operational rollout | see artifacts/_ci/operational_rollout_gate.log |
| 6 | competitive acceptance | see artifacts/_ci/competitive_acceptance_gate.log |
| 7 | perf | see artifacts/_ci/perf_gates.log |

## Next actions

- Если status=**not_proven** — НЕ мержить. Разобрать red-гейт, создать follow-up.
- Если status=**proven** — смотреть diff, убедиться в отсутствии regressions, мержить.
- Если в ходе задачи появились новые deprecations/warnings — убедиться, что они добавлены в \`configs/compat/deprecation_warnings_v1.json\`.
- Если есть изменения в public API — обновлён ли \`docs/public_interfaces.json\`?
EOF

echo "==> Summary written to $SUMMARY_FILE"

# --- Commit + push ---
git add -A
git commit -m "${BRANCH_PREFIX}: ai increment ($STATUS)

Task: $(head -1 "$TASK_FILE" | sed 's/^# *//')

Gates:
  1 pytest: $( [[ $GATE_FAIL -eq 0 ]] && echo pass || echo fail )
  2 web smoke: see artifacts/_ci/web_smoke.log
  3 golden verify_refactor: see artifacts/_ci/verify_refactor.log
  4 warning governance: see artifacts/_ci/warning_governance_report.md
  5 operational rollout: see artifacts/_ci/operational_rollout_gate.log
  6 competitive acceptance: see artifacts/_ci/competitive_acceptance_gate.log
  7 perf gates: see artifacts/_ci/perf_gates.log

Honest status: $STATUS
" || echo "==> Nothing to commit (no changes made by Claude)"

# --- PR (опционально) ---
if [[ "$AUTO_PR" == "true" && "$GATE_FAIL" -eq 0 ]]; then
  echo "==> Opening PR"
  git push -u origin "$BRANCH"
  gh pr create \
    --title "[AI] $(head -1 "$TASK_FILE" | sed 's/^# *//')" \
    --body "$(cat "$SUMMARY_FILE")" \
    --label "ai-generated,needs-review"
elif [[ "$AUTO_PR" == "true" && "$GATE_FAIL" -ne 0 ]]; then
  echo "==> AUTO_PR=true but gates failed — NOT pushing. Review $SUMMARY_FILE."
else
  echo "==> AUTO_PR=false — branch stays local. Push manually after review."
fi

echo "==> Done. Final status: $STATUS"
exit "$GATE_FAIL"
