# PMV-B01 Execution Proof — KPI Bridge

## Scope
Created `web_cabinet/analytics/kpi_bridge.py` — a facade that routes UI Dashboard KPI
requests through `genomeai.kpi_v2.run_kpi()` without duplicating computation logic.

## Files created
- `web_cabinet/analytics/__init__.py`
- `web_cabinet/analytics/kpi_bridge.py` (152 LoC — under 250 limit)
- `web_cabinet/analytics/tests/__init__.py`
- `web_cabinet/analytics/tests/test_kpi_bridge.py` (16 tests)

## Executed checks

```
pytest web_cabinet/analytics/tests/test_kpi_bridge.py -v
```

Result:
```
16 passed in 0.61s
```

Tests cover:
- `test_get_kpi_helper_*` (5) — helper unit tests
- `test_confidence_levels_*` (5) — confidence logic (high/medium/low)
- `test_dashboard_kpi_*` (2) — dataclass contract
- `test_compute_dashboard_kpi_synthetic` — happy path on target_v2 fixtures (FARM_001)
- `test_compute_dashboard_kpi_raw_kpi_long_attached` — drill-down DataFrame attached
- `test_compute_dashboard_kpi_empty_input` — empty dir → low confidence, all None
- `test_compute_dashboard_kpi_wrong_farm_id_returns_low_confidence` — unknown farm_id

## Net result

- `compute_dashboard_kpi('FARM_001', date(2024,6,1))` returns a populated DashboardKPI
  with `avg_milk_yield_kg`, `fat_pct`, `protein_pct`, `scc_bulk_k` from fixtures.
- `compute_dashboard_kpi('demo-farm-v1', date.today())` returns `confidence="low"`,
  all numeric fields `None` — expected (no fixture data for that farm_id).
- Fields `ecm_kg`, `pregnancy_rate_21d_pct`, `days_open_avg` are `None` — placeholder
  for Week 4 (KPI not present in kpi_v2 yet; documented in code).

## Honest status

**partially_proven** — bridge tests green locally; full 7-gate CI not run (no live
Postgres/Redis in this worktree context). Gates 1/7 (pytest) passes for this module.
Gates 2–7 require the full adult docker-compose contour.
