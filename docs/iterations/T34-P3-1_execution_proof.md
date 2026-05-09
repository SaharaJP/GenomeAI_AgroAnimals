# T34-P3-1 Execution Proof — Additive Decomposition Before Welch

**Date:** 2026-05-09
**Source brief:** `docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md` §P3-1
**Plan:** `docs/superpowers/plans/2026-05-09-p3-1-additive-impact-decomposition.md`
**Thesis source:** §3.2.2, формулы 3.6–3.10, табл. 3.5.5

## Scope

Inject additive decomposition `K(t) = T(t) + S(t) + E(t) + ε(t)` (formula 3.7) before the Welch t-test in the impact-validation pipeline so the effect estimate `ΔK_adj` (formula 3.8) is uncorrupted by linear trend and (where data permits) calendar-day seasonality.

Phase 0 verification (per brief §P3-1 Step 1): no decomposition in current code — production path goes raw Welch via `web_cabinet/analytics/statistical_extension.py:161` and `scripts/validate_mastitis_model.py:294`. Proceeded to brief §P3-1 Step 2 (build module).

## Commits

| # | SHA | Subject |
|---|-----|---------|
| 0 | `094e85d` | docs(P3-1): plan for additive impact decomposition before Welch |
| 1 | `b878b5d` | feat(P3-1): additive K(t)=T+S+E+ε decomposition module |
| 2 | `3e1e063` | feat(P3-1): apply additive decomposition before Welch in impact validation |
| 3 | `d5feb96` | test(P3-1): table 3.5.5 acceptance — 4/5 mastitis events significant |

## Acceptance — table 3.5.5 of the diploma

| Event | Cow | Severity | dM (raw) | p (raw) | dM_adj | p (decomp) | Verdict | Match |
|---|---|---|---:|---:|---:|---:|---|---|
| EV_4821_MAST_01 | 4821 | severe | -7.64 | 0.0000 | -7.90 | 0.0000 | **significant** | ✅ |
| EV_3891_MAST_01 | 3891 | severe | -5.39 | 0.0001 | -3.95 | 0.0018 | **significant** | ✅ |
| EV_3891_MAST_02 | 3891 | severe | -4.56 | 0.0003 | -3.08 | 0.0066 | **significant** | ✅ |
| EV_3002_MAST_01 | 3002 | mild   | -0.31 | 0.7546 | -1.61 | 0.0649 | **NOT significant** | ✅ |
| EV_3010_MAST_01 | 3010 | severe | -3.46 | 0.0000 | -2.37 | 0.0005 | **significant** | ✅ |

**Result: 4/5 significant, EV_3002 not significant — exactly matches the thesis table 3.5.5 verdict.**

The decomposed `dM_adj` magnitudes are smaller than the raw `dM` because the natural lactation-curve trend (cows produce less milk over a normal lactation independent of disease) is removed. EV_3002's p-value moves from 0.7546 to 0.0649 — much closer to the 0.05 threshold but still not crossing it, which is consistent with the "mild form" classification in the thesis.

## Module exports — `web_cabinet/ai/impact_decomposition.py`

| Function | Purpose |
|---|---|
| `estimate_trend(values, dates, exclude_window) -> (a, b)` | OLS `T̂(t)=a+bt` on data outside the event window. Falls back to `(mean, 0)` if <3 points. |
| `estimate_seasonality(values, dates) -> dict[(month,day), float]` | Per-calendar-day mean deviation from global mean. Returns `{}` if span <365 days (per brief fallback). |
| `compute_adjusted_delta(values, dates, event_date, window_days)` | Formula 3.8: `ΔK_adj = mean(post_resid) − mean(pre_resid)`. |
| `decompose_for_welch(values, dates, event_date, window_days)` | Wire-ready `(pre, post)` residual arrays for `scipy.stats.ttest_ind(equal_var=False)`. |

## Tests

- `tests/web_cabinet/ai/test_impact_decomposition.py` — **11 unit tests** (trend recovery, exclude-window correctness, fall-back, seasonality empty/non-empty, adjusted-delta on synthetic step+ramp, Welch-array shape).
- `tests/test_impact_decomposition_acceptance.py` — **6 acceptance tests** (4 severe-form events significant, 1 mild not significant, 1 aggregate verdict).
- Regression smoke (no changes expected): 60/60 pass across `test_t34_statistical_robustness.py`, `test_impact_narrative.py`, `test_impact_endpoint.py`.

## Executed CI gates (CLAUDE.md §4)

All seven gates run on HEAD `d5feb96`. Artefacts in `artifacts/_ci/p3-1-gates/`.

| # | Gate | Exit | Marker | Artefact |
|---|------|------|--------|----------|
| 1 | pytest gate | 0 | `[ci_gate] === PASSED ===` | `gate1_pytest.log` |
| 2 | web smoke | 0 | `WEB_SMOKE_OK` | `gate2_web_smoke.log`, `web_smoke.json` |
| 3 | golden verify_refactor | 0 | `VERIFY_REFACTOR_OK` (2 scenarios, 11 files, 0 diffs each) | `gate3_golden.log` |
| 4 | warning governance | 0 | `WARNING_GOVERNANCE_OK` | `gate4_warning.log` |
| 5 | operational rollout | 0 | `OPERATIONAL_ROLLOUT_GATES_OK` | `gate5_operational.log` |
| 6 | competitive acceptance | 0 | `COMPETITIVE_ACCEPTANCE_OK=true` | `gate6_competitive.log` |
| 7 | performance | 0 | `PERF_GATES_OK` (startup 2.5s, pipeline 0.6s, web_smoke 4.2s, verify_refactor 0.9s) | `gate7_perf.log` |

## Honest status

`proven`.

- All 7 CLAUDE.md §4 gates green at HEAD `d5feb96`.
- Thesis table 3.5.5 verdict locked: 4/5 mastitis events significant, EV_3002_MAST_01 not significant.
- 11/11 unit tests + 6/6 acceptance tests + 60/60 regression tests green.
- Backup of pre-P3-1 raw-Welch results saved at `scripts/validation_results.json.bak_pre_p3_1` for diff inspection.

## Out of scope (per plan)

- Multi-year seasonal modelling — demo dataset has <1 year history; `estimate_seasonality` returns `{}` (seasonal=0 fallback per brief §P3-1).
- Wiring decomposition into `compute_full_impact` (synthetic-data path) — kept synthetic-only for unit tests; real-data wiring is in the validation script.
- Production wiring into FastAPI `/api/ai/impact-narrative` endpoint — currently demo-only seeded JSON; live KPI warehouse not yet implemented (see `PATHFINDER-2026-05-09/01-flowcharts/timeline-events-and-impact.md` Gap 1).

## From координатора

— Nothing blocking. Branch ready to push.
