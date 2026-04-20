# T15-08 step 2 — reporting use cases in core

## Что сделано
- Добавлен `src/core/reporting/use_cases.py`.
- Вынесена orchestration-логика для:
  - assistant report (`run_assistant_report_use_case`),
  - regular reports (`run_regular_report_use_case`),
  - template reports finalization (`run_template_report_use_case`).
- Legacy entrypoints `genomeai.report.run_report`, `genomeai.regular_reports.run_regular_report`, `genomeai.template_reports.run_template_report` превращены в thin wrappers.
- Для template reports сохранена старая focus-filter логика по `object_type/object_id` и `related_alert`.

## Проверка
```bash
pytest -q tests/test_t15_08_reporting_core_step1.py \
  tests/test_t15_08_reporting_core_step2.py \
  tests/test_a5_report.py \
  tests/test_t8_01_regular_reports.py \
  tests/test_t10_04_template_report_generation.py \
  tests/test_t10_04_template_report_focus_filter.py \
  tests/test_t15_07_ml_consumers_step4.py

bash scripts/smoke_offline.sh
python -m genomeai verify_refactor --project-root . --golden golden --report-root /tmp/t15_08_verify_step2 --scenarios standard
```

## Ограничение шага
- Текстовые narrative/template markdown builders пока ещё живут в legacy-модулях; в core вынесена именно orchestration/finalization/persistence/use-case логика.
