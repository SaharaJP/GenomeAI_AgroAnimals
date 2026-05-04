# PMV-B02b Execution Proof — /api/dashboard/today wired to kpi_bridge

## Scope

Wire `/api/dashboard/today` endpoint to `kpi_bridge.compute_dashboard_kpi()`.
Branch on `GENOMEAI_AI_DEMO_MODE`: demo → seeded JSON, real → computed KPIs.

## Files changed

| File | Change |
|------|--------|
| `web_cabinet/analytics_v1.py` | +73 lines: imports, 4 helpers, 1 endpoint |
| `data/demo/investor_v1/dashboard_today_seeded.json` | New — seeded KPI payload for demo mode |
| `web_cabinet/analytics/tests/test_dashboard_endpoint.py` | New — 6 tests (TDD, RED→GREEN) |
| `web_cabinet/analytics/tests/conftest.py` | New — adds `src/` to sys.path for analytics_v1 import |

## Design

```
GET /api/dashboard/today?farm_id=<str>
    │
    ├─ GENOMEAI_AI_DEMO_MODE=true  → _load_seeded_dashboard()
    │                                  ← data/demo/investor_v1/dashboard_today_seeded.json
    │                                  ← {"demo": true, "confidence": "high", ...}
    │
    └─ GENOMEAI_AI_DEMO_MODE=false → compute_dashboard_kpi(farm_id, date.today())
                                       via kpi_v2.run_kpi()
                                       ← {"demo": false, "confidence": ..., ...}
```

## Executed checks

### 1. TDD cycle (RED → GREEN)
```
RED:  6 tests FAILED — AttributeError: module has no attribute '_get_ai_settings'
      (confirmed tests fail for the right reason: feature not yet implemented)

GREEN: 6 tests PASSED after implementation
      web_cabinet/analytics/tests/test_dashboard_endpoint.py — 6/6 ✓
```

### 2. Full analytics test suite
```
web_cabinet/analytics/tests/ — 26 passed, 0 failed (16 kpi_bridge + 4 alerts_bridge + 6 new)
```

### 3. Regression baseline
```
Before my changes: 59 failed, 473 passed, 110 skipped (pre-existing failures)
After  my changes: 53 failed, 479 passed, 110 skipped
Net: −6 failures (exactly the 6 new tests now passing), 0 regressions
```

### 4. CI gate
```
bash scripts/run_ci_gate.sh → PASSED
  OK Python syntax check passed
  OK No frontend changes
  OK No secrets leaked
  OK web_cabinet imports OK
```

### 5. Warning governance gate
```
bash scripts/run_warning_governance_gate.sh → WARNING_GOVERNANCE_OK
```

### 6. Web smoke / healthz
```
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean → WEB_SMOKE_OK
  /healthz: ✓
  Full pipeline run: ingest → qc → train → score → report → pack → ✓
```

## Acceptance criteria check

| Criterion | Status |
|-----------|--------|
| Toggle GENOMEAI_AI_DEMO_MODE works | ✓ — tested via monkeypatch in test_endpoint_demo_mode_returns_seeded / test_endpoint_real_mode_returns_computed |
| Real mode calls kpi_v2 via bridge | ✓ — test_endpoint_real_mode_compute_called_with_correct_args verifies call args |
| /healthz still ok | ✓ — WEB_SMOKE_OK |
| Frontend renders (web smoke covers app startup) | ✓ — WEB_SMOKE_OK (no JS errors; Next.js not checked, app server starts cleanly) |

## Honest status

**partially_proven**

Proven:
- Endpoint branching logic is correct (unit-tested, monkeypatched)
- Seeded JSON loads and has all required keys
- `_kpi_to_dict` serializes all fields, excludes raw DataFrame
- `compute_dashboard_kpi` is called with correct args in real mode
- App starts cleanly, /healthz returns 200
- No regressions in test suite

Not proven (no runtime):
- End-to-end HTTP call to `/api/dashboard/today` with a real authenticated user
- Real mode against a live kpi_v2 fixture run on this endpoint path
- Frontend Next.js dashboard component rendering (no browser check done)
