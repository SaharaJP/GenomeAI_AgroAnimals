# T34-P1-1e Execution Proof — Page Consolidation

**Date:** 2026-05-09
**Plan:** docs/superpowers/plans/2026-05-09-p1-1e-page-consolidation.md
**Source:** Conversation 2026-05-09 — sidebar discoverability + dead-page cleanup

## Scope

Consolidate 4 active "duplicate" pages into their canonical targets and
delete 2 truly-dead pages, reducing the protected page set from 26 to
24 directories (4 source pages remain as one-line redirect shims
for one release cycle, ~2026-06-09).

## Commits

```
77e36cf feat(P1-1e): consolidate /assistant into /copilot
08f889b feat(P1-1e): consolidate /reports into /analytics tab
de558c7 feat(P1-1e): consolidate /planner into /timeline
514f8ab feat(P1-1e): consolidate /alerts into /insights
bfc72f0 chore(P1-1e): remove dead /design-system and /weekly-brief pages
ebe8f05 chore(P1-1e): drop dead pathLabels, add /admin/ai, fix validate-foundation path
```

## Per-pair acceptance

| Pair | Status | Evidence |
|---|---|---|
| /design-system → delete | ✅ | bfc72f0 |
| /weekly-brief → delete  | ✅ | bfc72f0 |
| /alerts → /insights     | ✅ | 514f8ab + 3 hrefs updated |
| /planner → /timeline    | ✅ | de558c7 + WeeklyPlansSection ported |
| /reports → /analytics   | ✅ | 08f889b + ReportsTab + URL ?tab=reports |
| /assistant → /copilot   | ✅ | 77e36cf + ExplainPanel + 9 hrefs updated |

## Route inventory (post-consolidation)

Protected page set: 24 directories total (down from 26).

```
admin, alerts*, analytics, assistant*, connections, copilot,
daily-summary, dashboard, decisions, economics, insights,
observability, pilot, planner*, profiles, readiness, reports*,
reproduction, settings, support, timeline, treatments, vet, worklists
```

`*` = redirect shim (one-line redirect to canonical target, kept for
deprecation cycle ending ~2026-06-09).

Truly removed: `design-system`, `weekly-brief` (2 directories deleted).

## Cleanup (ebe8f05)

**topbar.tsx pathLabels:**
- Removed `/design-system: 'Дизайн-система'` — page deleted Phase 1
- Removed `/assistant: 'Помощник'` — now a redirect shim; breadcrumb won't render
- Added `/admin/ai: 'AI-наблюдаемость'` — canonical Russian label for admin observability page

**validate-foundation.mjs:**
- Updated `mustExist` path from `components/reports/report-view-surface.tsx`
  to `components/analytics/reports/report-view-surface.tsx` to reflect
  the rename in commit 08f889b (Phase 4 /reports→/analytics consolidation).
  This fixed gates 5 and 6 which initially failed due to the stale path.

## Executed gates (CLAUDE.md §4)

| # | Gate | Exit | Artefact |
|---|------|------|----------|
| 1 | pytest | 0 | artifacts/_ci/p1-1e_pytest.log |
| 2 | web smoke | 0 | artifacts/_ci/p1-1e_web_smoke.{log,json} |
| 3 | verify_refactor | 0 | artifacts/_ci/p1-1e_verify_refactor.log |
| 4 | warning governance | 0 | artifacts/_ci/p1-1e_warnings.log |
| 5 | operational rollout | 0 | artifacts/_ci/p1-1e_rollout.log |
| 6 | competitive acceptance | 0 | artifacts/_ci/p1-1e_competitive.log |
| 7 | perf gates | 0 | artifacts/_ci/p1-1e_perf.log |

Note: Gates 5 and 6 initially failed (EXIT=2) because `validate-foundation.mjs`
still referenced the old path `components/reports/report-view-surface.tsx`
after the Phase 4 rename. Fixed in ebe8f05 before final proof.

### Gate 1 — pytest (exit 0)

```
[ci_gate] OK Python syntax check passed
[ci_gate] OK TypeScript typecheck passed
[ci_gate] OK No secrets leaked
[ci_gate] OK web_cabinet imports OK
[ci_gate] === PASSED ===
```

### Gate 2 — web smoke (exit 0)

```
WEB_SMOKE_OK
workdir=/opt/genomeai/repo/_tmp/p1-1e_smoke
data_version=dv_websmoke_20260509_124302
WEB_SMOKE_OK
```

### Gate 3 — verify_refactor (exit 0)

```
VERIFY_REFACTOR_OK
scenario=standard ok=True compared_files=11 differences=0
scenario=qc_issues ok=True compared_files=11 differences=0
```

### Gate 4 — warning governance (exit 0)

```
WARNING_GOVERNANCE_OK /opt/genomeai/repo/artifacts/_ci/warning_governance_report.json
```

### Gate 5 — operational rollout (exit 0, after ebe8f05 fix)

```
OPERATIONAL_ROLLOUT_GATES_OK
profile=enterprise_ci
gate=compile_daily_pages         ok=true within_budget=true duration_sec=0.001
gate=role_scenarios              ok=true within_budget=true duration_sec=0.000
gate=mobile_views                ok=true within_budget=true duration_sec=0.419
gate=worklists_profiles_reports  ok=true within_budget=true duration_sec=4.988
gate=rollout_diagnostics         ok=true within_budget=true duration_sec=0.009
```

### Gate 6 — competitive acceptance (exit 0, after ebe8f05 fix)

```
COMPETITIVE_ACCEPTANCE_OK=true
COMPETITIVE_ACCEPTANCE_READY_FOR_UAT=true
SCENARIO daily_operations:   automated_ok=true  overall=ready_for_manual_signoff
SCENARIO reproduction:       automated_ok=true  overall=ready_for_manual_signoff
SCENARIO vet:                automated_ok=true  overall=ready_for_manual_signoff
SCENARIO reports_worklists:  automated_ok=true  overall=ready_for_manual_signoff
SCENARIO mobile:             automated_ok=true  overall=ready_for_manual_signoff
SCENARIO migration:          automated_ok=true  overall=ready_for_manual_signoff
COMPETITIVE_ACCEPTANCE_SET_READY
```

### Gate 7 — perf gates (exit 0)

```
PERF_GATES_OK
profile=ci
gate=startup           ok=true within_budget=true duration_sec=2.384
gate=pipeline_smoke    ok=true within_budget=true duration_sec=0.603
gate=web_smoke         ok=true within_budget=true duration_sec=4.160
gate=verify_refactor   ok=true within_budget=true duration_sec=0.892
```

## Out of scope

- Removing the 4 redirect-shim pages (`/alerts`, `/planner`, `/reports`,
  `/assistant`) — kept for one release cycle; removal scheduled ~2026-06-09
  after telemetry confirms zero direct traffic
- Backend route deprecation (e.g. `/api/planner`, `/api/reports/*`) — out
  of P1-1e; consumers now route through consolidated frontend pages
- Mobile UX of the new consolidated layouts — desktop-only verified

## Honest status

`proven` — all 7 CI gates exit 0 after ebe8f05 fix. The validate-foundation
stale path was a P1-1e-introduced regression (from the Phase 4 rename in
08f889b) caught and fixed within this phase before the proof commit.
No pre-existing failures masked; no gate suppressions used.
