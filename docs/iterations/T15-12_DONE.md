# T15-12 — Cleanup дублей + CI гейты

## Что сделано
1. Удалены из корня репозитория временные regression-логи/pytest chunk-файлы предыдущих прогонов.
2. Добавлен `.gitignore`, чтобы такие файлы и CI scratch-артефакты больше не засоряли репозиторий.
3. Добавлен `ci/pytest_gate.txt` — единый обязательный pytest-набор для PR gates.
4. Добавлен `scripts/run_ci_gate.sh` для локального воспроизведения CI pytest-гейта.
5. Обновлён GitHub Actions workflow: `pytest` + `web_cabinet.smoke` + `verify_refactor`.
6. При падении workflow публикует CI artifacts с pytest/junit, smoke-логами и Golden diff-отчётами.
7. Обновлены `README.md` и `docs/project_map.md`; добавлен `docs/ci_gates.md`.
8. Добавлены тесты, фиксирующие наличие обязательных CI gates и публикацию failure artifacts.

## Что осталось инвариантным
- CLI/API/UI surface не менялся.
- Golden verification и backward-compatible shims сохранены.
- Web/Streamlit по-прежнему используют core-first подход без переноса бизнес-логики обратно в UI.
