# T10-02 Step7 — Director dashboards 3.0: trend exceptions (исключения)

## Что добавлено

1) Конфиг порогов/параметров для «исключений» трендов: `configs/kpi/kpi_trend_exceptions_v1.yaml`.
2) Offline-core расчёт `milk_trend_exceptions` из витрины `milk_trend_windows`:
   - severity (WARN/ALERT) по абсолютному изменению `change_pct`.
   - пояснение содержит `source_table`, `source_path`, `data_version`, `run_id`.
3) Экспорт snapshot `director_summary` всегда пишет `milk_trend_exceptions.csv` (может быть пустым) и лист `milk_exceptions` в XLSX.
4) В UI Director Summary показана таблица trend exceptions с фильтрами severity и window.

## Артефакты

- `artifacts/<data_version>/runs/<dashboard_run_id>/dashboards/director_summary/milk_trend_exceptions.csv`
- `director_summary.xlsx` (sheet: `milk_exceptions`)

## Как проверить

1) Запустить KPI и snapshot:

```bash
python -m genomeai.cli kpi --data-version dv_demo --input-dir data/fixtures/target_v2 --asof-date 2025-01-05 --run-id kpi_demo
python -m genomeai.cli dashboard --data-version dv_demo --kpi-run-id kpi_demo --input-dir data/fixtures/target_v2 --asof-date 2025-01-05 --run-id dash_demo
```

2) Проверить, что в папке snapshot есть файл:

```bash
ls -la artifacts/dv_demo/runs/dash_demo/dashboards/director_summary | grep milk_trend_exceptions.csv
```

3) Проверить UI:

```bash
streamlit run streamlit_app/Home.py
```

Открыть `Director Summary` → блок `Trends 7/30/90` → секция `Trend exceptions`.
