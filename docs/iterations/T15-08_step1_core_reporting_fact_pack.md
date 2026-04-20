# T15-08 step 1 — core reporting/fact-pack foundation

## Что сделано
- Добавлен новый пакет `core.reporting`.
- Вынесены shared fact-pack builders:
  - `core.reporting.fact_pack.build_assistant_fact_pack`
  - `core.reporting.fact_pack.build_regular_fact_pack`
- Вынесен shared deterministic MD/HTML/PDF/persist helper:
  - `core.reporting.report_builder.persist_fact_pack_bundle`
  - `core.reporting.report_builder.write_markdown_report_bundle`
- Legacy API сохранён:
  - `genomeai.report.build_fact_pack` → alias на core
  - `genomeai.regular_reports.build_fact_pack_regular` → alias на core
- `regular_reports` и `template_reports` переведены на shared report bundle writer без изменения layout артефактов.

## Проверка
- `pytest -q tests/test_t15_08_reporting_core_step1.py tests/test_a5_report.py tests/test_t8_01_regular_reports.py tests/test_t10_04_template_report_generation.py tests/test_t10_04_template_report_focus_filter.py tests/test_t15_07_ml_consumers_step4.py`
- `bash scripts/smoke_offline.sh`
- `python -m genomeai verify_refactor --project-root . --golden golden --report-root /tmp/t15_08_verify --scenarios standard`

## Ограничения следующего шага
- `genomeai.report.run_report`, `genomeai.regular_reports.run_regular_report` и `genomeai.template_reports.run_template_report` пока ещё orchestrate из legacy-модулей.
- Следующий безопасный шаг T15-08: вынести orchestration/report summary assembly в `core.reporting.report_builder`, оставить в legacy только thin wrappers.
