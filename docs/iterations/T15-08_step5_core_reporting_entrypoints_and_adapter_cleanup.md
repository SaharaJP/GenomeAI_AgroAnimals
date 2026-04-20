# T15-08 / step 5 — canonical core.reporting entrypoints + adapter cleanup

## Что сделано
- Добавлен `src/core/reporting/entrypoints.py` с canonical high-level entrypoints:
  - `run_assistant_report`
  - `run_regular_report`
  - `run_template_report`
- Entry points закрывают wiring use-cases + core builders/renderers и дают единый импорт для CLI/UI.
- Legacy `genomeai.report`, `genomeai.regular_reports`, `genomeai.template_reports` сведены ещё ближе к shim-уровню: `run_*` делегируют в новые core entrypoints.
- First-party adapters переведены на core imports:
  - `src/genomeai/cli.py`
  - `src/genomeai/smoke.py`
  - `src/genomeai/run_reproduce.py`
  - `streamlit_app/pages/10_Regular_Reports.py`
  - `streamlit_app/pages/18_Report_Templates.py`

## Почему это безопасно
- Сигнатуры публичных legacy функций не изменены.
- Имена файлов, layout артефактов, fact-pack/golden surface остаются прежними.
- UI/CLI now use one canonical builder path in core, while old imports keep working.

## Проверка
- Целевые regression tests на wrapper delegation и adapter import surface.
- `smoke_offline.sh`.
- `verify_refactor --scenarios standard`.
- Отдельный regression-pass `pytest -q` по всему репозиторию выполнен chunk-by-chunk, чтобы обойти лимиты среды исполнения без потери покрытия.

## Full regression-pass
- chunk_00: 65 passed
- chunk_01: 52 passed
- chunk_02: 47 passed
- chunk_03: 47 passed
- chunk_04: 56 passed
- chunk_05: 46 passed
- chunk_06: 45 passed
- chunk_07_clean: 7 passed
- Total: 365 passed
