# T34-P1-2c Execution Proof — Production-Grade NPV Upgrades

**Date:** 2026-05-09
**Source brief:** docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md §P1-2
**Plan:** docs/superpowers/plans/2026-05-09-p1-2c-production-grade-npv.md
**Predecessors:** P1-2 (`abe64f0`..`b3f107b`), P1-2b (`49cca7a`)

## Scope

Replace stub-grade approximations in the NPV cull/keep model with
literature-backed production-grade components:

1. **Phase 1.** Parity-stratified monthly cull-prob (Compton 2017)
   replaces flat 0.022/mo for the breed.
2. **Phase 2.** Animal age (years from `birth_date`) added as composite
   health-score component when >5 yrs (linear, capped 4.0).
3. **Phase 3.** Days-open (DIM > 150 with no successful breeding after
   the latest calving) and treatment-recurrence (≥2 same-type
   treatments inside 60 days) added as composite components.
4. **Phase 4.** Per-cow Wood (1967) lactation curve fit via
   `scipy.optimize.curve_fit` on `milk_yields.json`; Holstein defaults
   on insufficient/implausible fits.
5. **Phase 5.** Narrative-md "Ограничения модели" block updated to
   reflect new reality. No weight calibration was needed — Малина/
   Звёздочка acceptance held throughout.

## Commits

| # | SHA | Subject |
|---|-----|---------|
| 0 | `5a86400` | docs(P1-2c): plan for production-grade NPV upgrades |
| 1 | `60d73f3` | feat(P1-2c): parity-stratified survival probability |
| 2 | `ca6dec4` | feat(P1-2c): add age signal to composite health score |
| 3 | `644b948` | feat(P1-2c): days-open + treatment-recurrence signals |
| 4 | `6fdada6` | feat(P1-2c): per-cow Wood-curve milk projection |
| 5 | `8b4c5a4` | docs(P1-2c): refresh model-limitations narrative |

## Acceptance (plan §Acceptance criteria)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | All Phase 1–4 unit tests pass | ✅ | 35 passed, 1 skipped (focused suite) |
| 2 | `_health_burden_signal` returns ≥7 component scores | ✅ | 8 score components: mastitis, late_dim, parity, scc, lameness, age, days_open, treatment_recurrence |
| 3 | `compute_npv_keep` uses parity-stratified survival | ✅ | `baseline_cull_prob` surfaced; varies by lactation_no |
| 4 | `_project_monthly_milk_wood` falls back gracefully | ✅ | 5 fallback paths covered (no_accessor, empty, insufficient, no_calving, implausible) |
| 5 | Малина (3891) → `cull` | ✅ | snapshot below: decision=cull, NPV_keep=48,825 < NPV_cull=169,691 |
| 6 | Звёздочка (4821) → `keep` | ✅ | snapshot below: decision=keep, NPV_keep=423,479 > NPV_cull=169,691 |

## API snapshot — before/after P1-2c (TestClient, demo store)

| Metric | 3891 (Малина) — P1-2 | 3891 — P1-2c | 4821 (Звёздочка) — P1-2 | 4821 — P1-2c |
|---|---:|---:|---:|---:|
| decision | cull | **cull** | keep | **keep** |
| NPV_keep, ₽ | 147,611 | **48,825** | 349,947 | **423,479** |
| NPV_cull, ₽ | 169,691 | 169,691 | 169,691 | 169,691 |
| health total_score | n/a (binary) | **9.72** | n/a (binary) | **0.96** |
| baseline_cull_prob | 0.0220 (flat) | **0.0200** (L3) | 0.0220 (flat) | **0.0200** (L3) |
| Wood fit | stylized decay | **per_cow_n180** (a=13.7) | stylized decay | **fallback_implausible** → defaults |
| firing components | recurrent_mastitis only | mastitis 3.0, late_dim 1.7, scc 1.02, days_open 3.0, treatment_recurrence 1.0 | none | scc 0.48, days_open 0.48 |

Малина's NPV_keep dropped from 147,611 → 48,825 ₽ as the new components
(late-DIM, chronic SCC, days-open, treatment recurrence) all fired on
top of the existing recurrent-mastitis signal — a more honest valuation.
Звёздочка's NPV_keep rose from 349,947 → 423,479 ₽: SCC and days-open
contribute mildly but the Wood-fallback default peak (a=25) lifts the
projected milk above the previous stylized decay. Decision flips
preserved on both cases.

Snapshot artefact: `artifacts/_ci/p1-2c/snapshot_after.json`.

## Focused test suite

```
tests/web_cabinet/ai/test_npv_cull.py + tests/web_cabinet/animals/
35 passed, 1 skipped, 38 warnings in 4.60s
```

Artefact: `artifacts/_ci/p1-2c/focused_pytest.log`. P1-2c-specific
additions to test coverage: 17 new tests (2 Phase 1, 5 Phase 2,
7 Phase 3, 5 Phase 4 — including parity ordering, age cap, days-open
cases, treatment-recurrence cases, Wood-fit recovery from synthetic
data, fallback paths, and `wood_params` surface check).

## Executed CI gates (CLAUDE.md §4)

All seven gates run on the working tree at HEAD `b85f585`. Artefacts
in `artifacts/_ci/p1-2c-gates/`.

| # | Gate | Exit | Marker | Artefact |
|---|------|------|--------|----------|
| 1 | pytest gate (`scripts/run_ci_gate.sh`) | 0 | `[ci_gate] === PASSED ===` | `gate1_pytest.log` |
| 2 | web smoke (`web_cabinet.smoke`) | 0 | `WEB_SMOKE_OK` | `gate2_web_smoke.log`, `web_smoke.json` |
| 3 | golden verify_refactor | 0 | `VERIFY_REFACTOR_OK` (2 scenarios, 11 files, 0 diffs each) | `gate3_golden.log`, `verify_refactor/verify_*/` |
| 4 | warning governance | 0 | `WARNING_GOVERNANCE_OK` | `gate4_warning.log`, `artifacts/_ci/warning_governance_report.json` |
| 5 | operational rollout | 0 | `OPERATIONAL_ROLLOUT_GATES_OK` (5/5 sub-gates within budget) | `gate5_operational.log`, `artifacts/_ci/operational_rollout_gates/*` |
| 6 | competitive acceptance | 0 | `COMPETITIVE_ACCEPTANCE_OK=true` (6/6 scenarios `ready_for_manual_signoff`) | `gate6_competitive.log`, `artifacts/_ci/competitive_acceptance/*` |
| 7 | performance | 0 | `PERF_GATES_OK` (4/4 sub-gates within budget: startup 2.5s, pipeline 0.6s, web_smoke 4.0s, verify_refactor 0.9s) | `gate7_perf.log`, `artifacts/_ci/performance_gates/*` |

Note: the previously-reported pre-existing failures on gates 5/6
(obs 374-376 in claude-mem) were already resolved by `6888981`
(`fix(ops): operational_rollout_gates references after page
consolidation`) and `e19e0d2` (page consolidation reversal); both
gates pass cleanly on this branch.

## Honest status

`proven`.

- All 7 CLAUDE.md §4 gates green at HEAD `b85f585`.
- Focused unit + endpoint suite for the changed modules (`web_cabinet/
  ai/npv_cull.py`, `web_cabinet/ai/context_helpers/demo_loader.py`,
  `web_cabinet/animals/cull_recommendation`): 35 passed, 1 skipped.
- Малина (3891) → cull, Звёздочка (4821) → keep — demonstrated via
  live `recommend()` call against the demo store with both decisions
  changing in the expected direction (Малина's NPV_keep dropped
  148k → 49k, Звёздочка's rose 350k → 423k).
- Composite signal expanded 5 → 8 score components; production-grade
  parity-stratified survival and per-cow Wood-curve projection wired
  in with documented fallback paths.

Out of scope for this `proven` claim (per plan §Out of scope):
multi-lactation projection beyond cyclic 305+60 reset, embryonic/
fetal loss modelling, heat detection from sensors, random-effects
Wood fit, and frontend UI for the recommendation.

## От координатора

— Nothing blocking. Branch is ready to push.

## Out of scope (per plan)

- Multi-lactation projection beyond cyclic 305+60 reset
- Embryonic/fetal loss modelling
- Heat detection signal from sensor data
- Random-effects per-cow Wood fit
- Frontend UI for the recommendation
