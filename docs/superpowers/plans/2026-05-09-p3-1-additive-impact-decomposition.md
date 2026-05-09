# P3-1 — Additive K(t) = T+S+E+ε Decomposition Before Welch

**Date:** 2026-05-09
**Source brief:** `docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md` §P3-1
**Thesis source:** §3.2.2, формулы 3.6–3.10, табл. 3.5.5
**Predecessor verification (Phase 1):** decomposition NOT yet implemented in repo. Production path goes raw Welch via `web_cabinet/analytics/statistical_extension.py:161` (synthetic data) and `scripts/validate_mastitis_model.py:294` (real demo data).

## Goal

Inject additive decomposition `K(t) = T(t) + S(t) + E(t) + ε(t)` before the Welch t-test so the effect estimate `ΔK_adj` (formula 3.8) is uncorrupted by linear trend and weekly/calendar seasonality. Confirms thesis §3.2.2 statistical pipeline.

## Phase 1 — `impact_decomposition` module (1 commit)

**Files:** `web_cabinet/ai/impact_decomposition.py` (new), `tests/web_cabinet/ai/test_impact_decomposition.py` (new).

### Step 1: `estimate_trend(values, dates, *, exclude_window) -> (a, b)`

Linear regression `T̂(t) = a + b·t` on (date, value) pairs **outside** the exclude_window (a `(start_date, end_date)` tuple). Use OLS via numpy.polyfit. If <3 points outside the window, fall back to `(global_mean, 0.0)`.

### Step 2: `estimate_seasonality(values, dates, *, today=None) -> dict[date, float]`

For each calendar day-of-year present in history, compute mean deviation from global mean across **prior years**. Returns `{date(any_year, m, d): offset}`. If history span < 365 days, returns `{}` (empty — seasonal=0 fallback per brief).

### Step 3: `compute_adjusted_delta(values, dates, event_date, *, window_days) -> dict`

Compute pre and post means of `K(t) - T̂(t) - S(t)` for windows `[event-window, event-1]` and `[event+1, event+window]`. Returns `{"pre_mean": ..., "post_mean": ..., "delta": ..., "trend": (a,b), "seasonal_keys": int}`.

### Step 4: `decompose_for_welch(values, dates, event_date, *, window_days) -> tuple[np.ndarray, np.ndarray]`

The wire-ready output: returns `(pre_residuals, post_residuals)` arrays — already trend+seasonal-subtracted — for direct feed into `scipy.stats.ttest_ind(equal_var=False)`.

### Step 5: Unit tests

- `test_estimate_trend_recovers_known_slope` — synthetic `y=2+0.5*t` on 60 days → a≈2, b≈0.5.
- `test_estimate_trend_excludes_event_window` — synthetic data with bump in window; trend fit should NOT be biased by the bump.
- `test_estimate_trend_falls_back_when_too_few_points` — 2 points outside → falls back to (mean, 0).
- `test_estimate_seasonality_empty_for_short_history` — 6 months of data → returns `{}`.
- `test_estimate_seasonality_recovers_weekly_pattern` — synthetic 2-year sinusoidal → seasonal_keys > 0; offsets correctly signed.
- `test_compute_adjusted_delta_subtracts_trend` — series with strong trend + sharp post-event drop → adjusted delta closely matches the drop, raw delta does not.
- `test_decompose_for_welch_returns_residual_arrays` — shape and dtype sanity.

### Step 6: Commit
```
feat(P3-1): additive K(t)=T+S+E+ε decomposition module
```

---

## Phase 2 — Wire into validate_mastitis_model.py (1 commit)

**Files:** `scripts/validate_mastitis_model.py`, `scripts/validation_results.json` (regenerated).

### Step 1: Replace raw windows with residuals

In the impact loop (`scripts/validate_mastitis_model.py:282-307`), after extracting `cow_data` for the cow, call `decompose_for_welch(values, dates, event_date, window_days=14)` and feed `pre, post = decomposed_pre, decomposed_post` to `stats.ttest_ind`.

### Step 2: Backup + regenerate `validation_results.json`

```bash
cp scripts/validation_results.json scripts/validation_results.json.bak_pre_p3_1
python scripts/validate_mastitis_model.py
```

Confirm 4/5 events still significant + EV_3002 still not significant. The numerical p-values may shift (decomposition removes some variance), but the verdict stays.

### Step 3: Commit
```
feat(P3-1): apply additive decomposition before Welch in impact validation
```

---

## Phase 3 — Acceptance test (1 commit)

**Files:** `tests/test_impact_decomposition_acceptance.py` (new).

Test reads `data/demo/investor_v1/milk_yields.json` and `events.json`, picks the 5 mastitis events from table 3.5.5 (EV_4821_MAST_01, EV_3891_MAST_01, EV_3891_MAST_02, EV_3002_MAST_01, EV_3010_MAST_01), runs `decompose_for_welch` per event + `ttest_ind`, asserts:
- 4 events have p < 0.05
- EV_3002_MAST_01 has p ≥ 0.05

Also: smoke-test that `compute_full_impact` (existing API in `web_cabinet/analytics/statistical_extension.py`) still runs without regression — no changes there, just confirm endpoint stays green.

### Commit
```
test(P3-1): table 3.5.5 acceptance — 4/5 mastitis events significant
```

---

## Phase 4 — Docs + 7 gates + execution proof (1 commit)

- [ ] Run all 7 CI gates (CLAUDE.md §4).
- [ ] Write `docs/iterations/T34-P3-1_execution_proof.md` mirroring T34-P2-1: scope, commits, acceptance table, gate run, honest status `proven`.
- [ ] Final commit + push.

---

## Acceptance criteria (plan-level)

- [ ] All Phase 1 unit tests green
- [ ] Phase 2 regenerated `validation_results.json` keeps the 4/5 verdict
- [ ] Phase 3 acceptance test passes
- [ ] All 7 CI gates green
- [ ] Honest status: `proven`

## Out of scope

- Multi-year seasonal modelling (demo data has <1 year history; seasonal=0 per brief).
- Wiring decomposition into `compute_full_impact` (synthetic-data path) — kept synthetic for unit tests.
- Wiring into FastAPI `/api/ai/impact-narrative` endpoint (currently demo-only seeded JSON; wiring real-data path is post-thesis work).
