#!/usr/bin/env bash
# scripts/setup_worktrees.sh
# Создаёт 3 git worktrees для параллельной работы Claude Code в Bridge Strategy v3.
# Запускается ОДИН раз из корня репозитория.
#
# Зачем 3 worktrees:
#   wt-bridge       — bridges (kpi/alerts/sensor) в web_cabinet/analytics/
#   wt-stat         — statistical extension + impact panel
#   wt-iot          — sensor ingestion + CSV import
#
# Зоны изоляции (чтобы НЕ было merge conflicts):
#   wt-bridge       трогает ТОЛЬКО web_cabinet/analytics/, web_cabinet/ai/context.py
#   wt-stat         трогает ТОЛЬКО web_cabinet/analytics/statistical_extension.py, 
#                                   web_app/components/timeline/impact-panel.tsx
#   wt-iot          трогает ТОЛЬКО web_cabinet/iot/, web_cabinet/import_endpoints.py

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREES_ROOT="$(dirname "$REPO_ROOT")/worktrees"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "main" && "$CURRENT_BRANCH" != "mvp-investor-demo" ]]; then
  echo "ERROR: текущая ветка = $CURRENT_BRANCH, нужна main или mvp-investor-demo"
  exit 1
fi

if ! git diff --quiet; then
  echo "ERROR: working tree dirty. Закоммить или stash перед созданием worktrees."
  exit 1
fi

echo "==> Создаём worktrees в $WORKTREES_ROOT"
mkdir -p "$WORKTREES_ROOT"

declare -A WORKTREES=(
  ["wt-bridge"]="b/bridge"
  ["wt-stat"]="b/stat"
  ["wt-iot"]="b/iot"
)

for WT_NAME in "${!WORKTREES[@]}"; do
  WT_PATH="$WORKTREES_ROOT/$WT_NAME"
  BRANCH="${WORKTREES[$WT_NAME]}"
  
  if [[ -d "$WT_PATH" ]]; then
    echo "    $WT_NAME уже существует — пропускаем"
    continue
  fi
  
  echo "==> $WT_NAME -> ветка $BRANCH"
  git worktree add "$WT_PATH" -b "$BRANCH" "$CURRENT_BRANCH"
  
  # Копируем конфигурационные файлы в worktree
  for FILE in CLAUDE.md .mcp.json .env.ai; do
    if [[ -f "$REPO_ROOT/$FILE" ]]; then
      cp "$REPO_ROOT/$FILE" "$WT_PATH/"
      echo "    скопирован $FILE"
    fi
  done
  
  # Копируем claude_iteration.sh
  mkdir -p "$WT_PATH/scripts"
  if [[ -f "$REPO_ROOT/scripts/claude_iteration.sh" ]]; then
    cp "$REPO_ROOT/scripts/claude_iteration.sh" "$WT_PATH/scripts/"
    chmod +x "$WT_PATH/scripts/claude_iteration.sh"
    echo "    скопирован scripts/claude_iteration.sh"
  fi
  
  # Symlink на venv (один venv на всех)
  if [[ -d "$REPO_ROOT/.venv" ]]; then
    ln -sf "$REPO_ROOT/.venv" "$WT_PATH/.venv"
    echo "    создан symlink .venv -> main repo .venv"
  fi
done

echo ""
echo "==> Worktrees созданы:"
git worktree list

echo ""
echo "==> Что дальше"
echo "1. Создай 3 tmux сессии:"
echo "   tmux new -s ai-bridge -d 'cd $WORKTREES_ROOT/wt-bridge'"
echo "   tmux new -s ai-stat -d 'cd $WORKTREES_ROOT/wt-stat'"
echo "   tmux new -s ai-iot -d 'cd $WORKTREES_ROOT/wt-iot'"
echo ""
echo "2. Копируй промпт в next_task.md и запускай:"
echo "   tmux a -t ai-bridge"
echo "   cp $REPO_ROOT/docs/iterations/PMV-B01_prompt.md next_task.md"
echo "   AUTO_PR=false bash scripts/claude_iteration.sh"
echo ""
echo "Успехов!"
