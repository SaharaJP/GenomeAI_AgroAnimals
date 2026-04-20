# T10-02 — Дашборды директора 3.0 (DONE)

## Цели итерации

1) **Система целей/порогов KPI** (farm/site) и отображение **план‑факт**.
2) **Тренды 7/30/90**, выявление **top‑отклонений** и их объяснение с привязкой к `run_id` и источникам данных.
3) Экспорт **dashboard snapshot** (PDF/PNG) и действие **«сохранить как отчет»**.

## Что реализовано

- **Targets/thresholds** в YAML: `configs/kpi/kpi_targets_v1.yaml` + override через `WEB_STORAGE_DIR/config_overrides/...`.
- **Plan‑fact mart**: `genomeai.kpi_targets.compute_plan_fact()`.
- **Top deviations vs targets**: `genomeai.dashboard_insights.compute_top_deviations()` (с `data_version`, `kpi_run_id`, `source_table/source_path`).
- **Trends 7/30/90 + trend exceptions**: `compute_milk_trend_windows()` + `compute_milk_trend_exceptions()` (CSV + XLSX sheet).
- **Snapshot export**: `genomeai.dashboard_director.export_director_summary()`
  - артефакты: `director_summary.xlsx`, `director_summary.pdf`, `director_summary.png` (+ CSV витрины)
  - манифест/чексаммы: `run_manifest.json`, `checksums.json`.
- **Save as report**: `genomeai.dashboard_reports.save_dashboard_snapshot_as_report()`
  - `reports/<report_version>/dashboard/<kind>/exports/...`
  - `metadata/dashboard_report_manifest.json`.
- **Web Cabinet UI (Streamlit)**:
  - Director Summary: цели/пороги, plan‑fact, deviations, trends/exceptions, export/download, save-as-report.
  - Dashboard Reports: список сохранённых отчётов и скачивание.
- **Audit log**: export/download/save‑as‑report/update targets.

## Как проверить (смоук)

```bash
cd <repo>
export PYTHONPATH=src

# 1) Тесты T10-02
pytest -q tests/test_t10_02_*.py

# 2) KPI → Director snapshot (пример на фикстурах)
python -m genomeai.cli kpi \
  --data-version dv_demo \
  --asof-date 2025-01-05 \
  --input-dir data/fixtures/target_v2 \
  --artifacts artifacts \
  --run-id kpi_demo \
  --config-kpi configs/kpi/kpi_v2.yaml \
  --config-thresholds configs/kpi/kpi_thresholds_v2.yaml

python -m genomeai.cli dashboard \
  --data-version dv_demo \
  --asof-date 2025-01-05 \
  --input-dir data/fixtures/target_v2 \
  --artifacts artifacts \
  --kpi-run-id kpi_demo \
  --run-id dash_demo

ls -la artifacts/dv_demo/runs/dash_demo/dashboards/director_summary | egrep "director_summary\\.(xlsx|pdf|png)"

# 3) Save snapshot as report
python - <<'PY'
from pathlib import Path
from genomeai.dashboard_reports import save_dashboard_snapshot_as_report

print(save_dashboard_snapshot_as_report(
    artifacts_root=Path('artifacts'),
    data_version='dv_demo',
    dashboard_run_id='dash_demo',
    dashboard_kind='director_summary',
    report_version='reportdash_demo',
    notes='smoke',
))
PY

ls -la artifacts/dv_demo/reports/reportdash_demo/dashboard/director_summary/exports
```

## Примечания

- PNG snapshot по умолчанию рендерится через **Pillow** (`configs/reports/director_snapshot_v1.yaml: png.renderer=pil`) — быстрее и стабильнее для perf-smoke.
- Если входных канонических таблиц для трендов нет, тренды/exceptions будут пустыми (best-effort), при этом экспорт и UI остаются рабочими.
