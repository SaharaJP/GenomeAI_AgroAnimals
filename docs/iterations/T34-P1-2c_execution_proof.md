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

| # | Gate | Status | Note |
|---|------|--------|------|
| 1 | pytest gate | not_proven | pre-existing repo-wide gate; outside this scope. focused suite (above) is `proven`. |
| 2 | web smoke | not_proven | not run in this session |
| 3 | golden verify_refactor | not_proven | not run; no contract changes in P1-2c |
| 4 | warning governance | not_proven | not run; no new filterwarnings introduced |
| 5 | operational rollout | not_proven | known pre-existing failure unrelated to P1-2c (frontend page consolidation residue, see obs 374-376) |
| 6 | competitive acceptance | not_proven | known pre-existing failure (ditto) |
| 7 | performance | not_proven | not run |

Per CLAUDE.md §10: not running all 7 gates ⇒ status cannot be `proven`.

## Honest status

`partially_proven`.

What is `proven`:

- The focused unit + endpoint test suite covering the changed module
  (`web_cabinet/ai/npv_cull.py`, `web_cabinet/ai/context_helpers/
  demo_loader.py`, `web_cabinet/animals/cull_recommendation` endpoint)
  passes 35/35 (1 skipped).
- Малина (3891) → cull, Звёздочка (4821) → keep, demonstrated via
  live `recommend()` call against the demo store.
- Composite signal expanded from 5 → 8 score components.
- Production-grade survival model and Wood-curve projection wired in,
  with documented fallback paths.

What remains `not_proven`:

- Full 7-gate CLAUDE.md run. Gates 5/6 carry pre-existing failures
  unrelated to P1-2c (frontend page consolidation residue, see obs
  374-376 in claude-mem). Other gates were not exercised in this
  session.
- UI surface for the new components (out of scope per plan §Out of
  scope; backend-only deliverable).

## From координатора

— Nothing blocking for the scope of P1-2c itself. Coordinator
decision needed before the next milestone: should the gate-5/6
pre-existing frontend failures be addressed before claiming a full
`proven` for this branch, or carried forward as a separate ticket?

## Out of scope (per plan)

- Multi-lactation projection beyond cyclic 305+60 reset
- Embryonic/fetal loss modelling
- Heat detection signal from sensor data
- Random-effects per-cow Wood fit
- Frontend UI for the recommendation
