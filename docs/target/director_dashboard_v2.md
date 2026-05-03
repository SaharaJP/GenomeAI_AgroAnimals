# Director Dashboard v2 — Summary + Drill-down (T1-02)

## Goal
Provide a fast, understandable **Director Summary** screen (mini-web, no BI) that reads reproducible KPI artifacts and supports drill-down and export.

## Screen: Director Summary (v2)
### Widgets
1. **KPI tiles** (top 12)
   - Source: `artifacts/<data_version>/runs/<kpi_run_id>/kpi/kpi_long.csv`
   - Formula: from `configs/kpi/kpi_v2.yaml` (`kpi_id`, `formula`, `sources`)
   - RBAC: `kpi.view`
   - Click → Drill-down page (KPI definition + rows for selected KPI)
2. **Trends 7/30/90**
   - Milk trend (daily total milk_kg last 90d): `dm_milkings_daily.csv` (input_dir for trends)
   - Alerts trend (optional): `dm_alerts.csv`
   - RBAC: `kpi.view`
3. **Top risks**
   - Source: `artifacts/<dv>/runs/<kpi_run_id>/kpi/kpi_alerts.csv`
   - Thresholds: `configs/kpi/kpi_thresholds_v2.yaml`
   - RBAC: `kpi.view`
4. **Top recommendations**
   - Source (when available): scoring/recommendations artifacts.
   - Current behavior: **graceful fallback** (shows message until scoring/report pipeline exists)
   - RBAC: `kpi.view`

## Drill-down
- KPI tile click → **KPI Drill-down** page:
  - Shows definition (title/description/formula/sources)
  - Shows rows for `kpi_id` from `kpi_long.csv`
- Future tasks will extend drill-down to site/pen/animal.

RBAC:
- View drill-down: `drilldown.view`

## Export
- Button "Generate snapshot" creates:
  - XLSX: `director_summary.xlsx` (sheets: kpi_wide/kpi_long/kpi_alerts)
  - PDF: `director_summary.pdf` (minimal textual snapshot)
- Written to:
  - `artifacts/<data_version>/runs/<dash_run_id>/dashboards/director_summary/`
- RBAC:
  - Export snapshot: `export.download`
- Audit:
  - In web cabinet, exports should be logged via `export.download`.
  - Streamlit export is currently offline; if needed, add explicit audit bridging later.

## Implementation
- Backend exports: `src/genomeai/dashboard_director.py`
- Streamlit app:
  - `streamlit_app/app.py`
  - Pages:
    - `streamlit_app/pages/1_Director_Summary.py`
    - `streamlit_app/pages/2_KPI_Drilldown.py`

## How to run
1) Ensure KPI exists:
```bash
genomeai kpi --data-version dv_demo --asof-date 2025-01-05 --input-dir data/fixtures/target_v2 --artifacts artifacts
```
2) Run Streamlit:
```bash
pip install streamlit
streamlit run streamlit_app/app.py
```
