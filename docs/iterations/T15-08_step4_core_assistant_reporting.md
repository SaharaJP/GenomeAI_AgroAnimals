# T15-08 — step 4

## Что сделано
- Добавлен модуль `src/core/reporting/assistant_reporting.py`.
- В него вынесены assistant-report narrative builders (`fallback` и `LLM`) и renderers (`DOCX` и `PDF`).
- `src/genomeai/report.py` переведен на thin wrappers для этих функций.
- Публичные entrypoints, сигнатуры и layout артефактов сохранены.
- Добавлены тесты на core exports и на то, что legacy helper-функции действительно делегируют в core.

## Проверка
```bash
pytest -q tests/test_t15_08_reporting_core_step1.py \
  tests/test_t15_08_reporting_core_step2.py \
  tests/test_t15_08_reporting_core_step3.py \
  tests/test_t15_08_reporting_core_step4.py \
  tests/test_a5_report.py \
  tests/test_t8_01_regular_reports.py \
  tests/test_t10_04_template_report_generation.py \
  tests/test_t10_04_template_report_focus_filter.py \
  tests/test_t12_03_playbooks_step3_ai_integration.py \
  tests/test_t14_04_explainability_step2.py \
  tests/test_t15_07_ml_consumers_step4.py

bash scripts/smoke_offline.sh

python -m genomeai verify_refactor \
  --project-root . \
  --golden golden \
  --report-root /tmp/t15_08_verify_step4 \
  --scenarios standard
```

## Результат
- pytest: green
- smoke_offline: `SMOKE_OK`
- verify_refactor: `VERIFY_REFACTOR_OK`
