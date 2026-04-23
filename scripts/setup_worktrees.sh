#!/usr/bin/env bash
# scripts/setup_worktrees.sh
# Создаёт 3 git worktrees для параллельной работы Claude.
# Запускается ОДИН раз из корня репозитория.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREES_ROOT="$(dirname "$REPO_ROOT")/worktrees"

# Убеждаемся что мы на нужной ветке
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "mvp-investor-demo" ]]; then
  echo "ERROR: текущая ветка = $CURRENT_BRANCH, нужна mvp-investor-demo"
  exit 1
fi

# Проверяем что нет незакоммиченных изменений
if ! git diff --quiet; then
  echo "ERROR: working tree dirty. Закоммить или stash перед созданием worktrees."
  exit 1
fi

echo "==> Создаём worktrees в $WORKTREES_ROOT"
mkdir -p "$WORKTREES_ROOT"

# Список worktrees: имя | ветка
declare -A WORKTREES=(
  ["wt-ui"]="mvp/ui"
  ["wt-ai-gateway"]="mvp/ai-gateway"
  ["wt-data"]="mvp/data"
)

for WT_NAME in "${!WORKTREES[@]}"; do
  WT_PATH="$WORKTREES_ROOT/$WT_NAME"
  BRANCH="${WORKTREES[$WT_NAME]}"
  
  if [[ -d "$WT_PATH" ]]; then
    echo "    $WT_NAME уже существует — пропускаем"
    continue
  fi
  
  echo "==> $WT_NAME -> ветка $BRANCH"
  git worktree add "$WT_PATH" -b "$BRANCH" mvp-investor-demo
  
  # Копируем конфигурационные файлы в worktree
  for FILE in CLAUDE.md .mcp.json .env.ai; do
    if [[ -f "$REPO_ROOT/$FILE" ]]; then
      cp "$REPO_ROOT/$FILE" "$WT_PATH/"
      echo "    скопирован $FILE"
    fi
  done
  
  # Копируем scripts/claude_iteration.sh
  mkdir -p "$WT_PATH/scripts"
  if [[ -f "$REPO_ROOT/scripts/claude_iteration.sh" ]]; then
    cp "$REPO_ROOT/scripts/claude_iteration.sh" "$WT_PATH/scripts/"
    chmod +x "$WT_PATH/scripts/claude_iteration.sh"
    echo "    скопирован scripts/claude_iteration.sh"
  fi
done

echo ""
echo "==> Worktrees созданы:"
git worktree list

echo ""
echo "==> Что дальше"
echo "1. Создай 3 tmux сессии:"
echo "   tmux new -s ai-ui -d 'cd $WORKTREES_ROOT/wt-ui'"
echo "   tmux new -s ai-backend -d 'cd $WORKTREES_ROOT/wt-ai-gateway'"
echo "   tmux new -s ai-data -d 'cd $WORKTREES_ROOT/wt-data'"
echo ""
echo "2. Копируй промпт в next_task.md и запускай:"
echo "   tmux a -t ai-ui"
echo "   cp $REPO_ROOT/docs/iterations/MVP-N01_prompt.md next_task.md"
echo "   AUTO_PR=false bash scripts/claude_iteration.sh"
echo ""
echo "Успехов!"
