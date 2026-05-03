# T15-08 step 3 — regular/template narratives and template preparation in core

## Что сделано
- Добавлен `src/core/reporting/regular_reporting.py`.
- В core перенесены deterministic regular-report builders:
  - `generate_regular_report_text_fallback`,
  - `generate_regular_report_text_llm`,
  - `render_regular_report_markdown`.
- Добавлен `src/core/reporting/template_reporting.py`.
- В core перенесена подготовка template-report fact-pack + markdown (`prepare_template_report_artifacts`) вместе с focus-filter/economics/KPI table helpers.
- Legacy `genomeai.regular_reports` и `genomeai.template_reports` теперь используют core-функции через thin wrappers/shims.
- Дополнительно исправлена совместимость `core.reporting.build_regular_fact_pack` с legacy shape: возвращены `modules.health.mastitis_risk`, `modules.mating` и `disclaimer`.

## Проверка
```bash
pytest -q tests/test_t15_08_reporting_core_step1.py \
  tests/test_t15_08_reporting_core_step2.py \
  tests/test_t15_08_reporting_core_step3.py \
  tests/test_a5_report.py \
  tests/test_t8_01_regular_reports.py \
  tests/test_t10_04_template_report_generation.py \
  tests/test_t10_04_template_report_focus_filter.py \
  tests/test_t12_03_playbooks_step3_ai_integration.py \
  tests/test_t14_04_explainability_step2.py \
  tests/test_t15_07_ml_consumers_step4.py

bash scripts/smoke_offline.sh
python -m genomeai verify_refactor --project-root . --golden golden --report-root /tmp/t15_08_verify_step3 --scenarios standard
```

## Ограничение шага
- Base assistant-report narrative/docx/pdf builders (`genomeai.report.generate_report_text_*`, `_render_docx`, `_render_pdf`) пока ещё остаются в legacy-модуле.
- Следующий безопасный шаг T15-08 — вынести assistant narrative/rendering в `core.reporting`, а legacy `genomeai.report` сократить до shim-уровня.
