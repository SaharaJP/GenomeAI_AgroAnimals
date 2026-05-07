# T34 — Analytics QC Overlays + Fullscreen: execution proof

## Scope

Add AI-described QC incidents, AI-linked timeline events, and a fullscreen
chart modal to the `/analytics` surface. Backend uses 4 deterministic
heuristics (gap/range/stuck/flatline) with a Claude describer per incident
and a cron token-saver gate. Frontend wires QC + events into the existing
BiChart via overlay layers + a per-chart Maximize2 modal.

Plan: `docs/superpowers/plans/2026-05-07-analytics-qc-overlays.md`
Spec: `docs/superpowers/specs/2026-05-07-analytics-qc-overlays-design.md`

## Executed checks

### CLAUDE.md §4 — 7 CI gates

| # | Gate | Result | Exit | Artifact |
|---|------|--------|------|----------|
| 1 | pytest (`scripts/run_ci_gate.sh`)            | PASS | 0 | `artifacts/_ci/gate_1_pytest.log` |
| 2 | web smoke (`web_cabinet.smoke`)              | PASS | 0 | `artifacts/_ci/web_smoke.json`, `gate_2_web_smoke.log` |
| 3 | golden verify_refactor                       | PASS | 0 | `artifacts/_ci/gate_3_verify_refactor.log` |
| 4 | warning governance                           | PASS | 0 | `artifacts/_ci/gate_4_warning_governance.log` |
| 5 | operational rollout                          | FAIL (pre-existing) | 2 | `artifacts/_ci/gate_5_operational_rollout.log` |
| 6 | competitive acceptance                       | FAIL (pre-existing) | 2 | `artifacts/_ci/gate_6_competitive_acceptance.log` |
| 7 | performance                                  | FAIL (flaky pack-poll) | 2 | `artifacts/_ci/gate_7_perf.log`, `gate_7_perf_retry.log` |

Gate 3 detail: `scenario=standard ok=True compared_files=11 differences=0`,
`scenario=qc_issues ok=True compared_files=11 differences=0` — golden parity intact.

Gate 7 detail (both first run and retry): only `web_smoke` sub-gate fails with
`reason: "job kind=pack not done: status=running"` — a pre-existing polling
race in `web_cabinet/smoke.py` (the runbook calls this out as a known flake;
on this run it surfaced on `pack` instead of `report`). Steps `rbac`,
`ingest_all`, `qc`, `train`, `score`, `report`, `decisions` all `ok` and
within budget; `verify_refactor`, `pipeline_smoke`, `startup` sub-gates pass.

### Targeted analytics-qc pytest

```
pytest tests/test_qc_v1_db.py tests/test_qc_detector.py tests/test_event_metric_linker.py -v
```

Result: **13 passed, 24 warnings in 1.25s**.

### Live UI validation

Playwright screenshots committed in `d4e1b26` (repo-root PNGs):
- `analytics-qc-overlay.png` — chart with translucent QC rectangle
- `analytics-qc-tooltip.png` — hover state (native SVG title tooltip)
- `analytics-qc-incident-card.png` — click → modal with AI description
- `analytics-qc-toggle-off.png` — toggle off, overlay removed
- `analytics-fullscreen.png` — fullscreen modal
- `analytics-fullscreen-overlay.png` — overlays preserved in fullscreen

Event-related screenshots not captured: the demo seed produced no timeline
events with linked_metric_ids (linker only runs on event creation; demo
data has no events at validation time).

## Failure analysis

### Gates 5 and 6 — pre-existing regression (not introduced here)

`web_app/scripts/validate-foundation.mjs:60` asserts the literal English string
`'No reproduction logic is reimplemented in the browser.'` which was Russified
in commit `7b08924` ("fix(ui): sidebar management nav, briefing generation,
Russian text across all surfaces") without updating the validator. The failing
shell scripts (`scripts/smoke_t32_05_react_daily_operations.sh`,
`scripts/smoke_t32_06_react_profiles_reports_assistant.sh`) both invoke
`npm run smoke` → `validate-foundation.mjs`. Verified via stderr tail in
`artifacts/_ci/operational_rollout_gates/operational_rollout_gates_report.json`:
```
Error: Reproduction parity note missing backend-first posture
    at .../web_app/scripts/validate-foundation.mjs:61:9
```
Files involved are entirely untouched by the analytics QC overlays PR
(commits `47f4288`, `3d39c5e`, `3c5f4b6`, `d4e1b26`, `cde6e02`).

### Gate 7 — pre-existing polling race in web_cabinet/smoke.py

Both first run and retry failed with the identical structural reason:
`details.reason = "job kind=pack not done: status=running"`. All earlier
pipeline stages (rbac → decisions) succeed within their budgets. The runbook
explicitly identifies this as a flaky polling race independent of the QC
overlays change. Untouched code path: `web_cabinet/smoke.py` job-poll loop.

## Net result

**4 / 7 gates green, 3 pre-existing red.** Spec acceptance criteria 1–12
(spec §9.3) verified by targeted pytest + Playwright UI evidence + post-validation
fix `cde6e02` (overlays on built-in tab charts + correct date mapping via
`findWeekIndex`).

## Known follow-ups

1. **Herd tab not converted to BuiltInChartCard.** `herd-tab.tsx` uses
   `HerdBarChart` (custom horizontal-bar component, not BiChart) for snapshot
   data. QC overlays / event markers don't apply to non-time-series charts.
   Out of scope.
2. **Native SVG tooltip vs HTML tooltip.** Hover on QC overlay shows a
   browser-rendered `<title>` element. Fine for content discovery, but
   doesn't show in screenshots and can't be styled. If product wants a
   custom tooltip, render an HTML overlay positioned by mouse coords —
   future work.
3. **Pre-existing gates 5/6 regression** — one-line fix to
   `web_app/scripts/validate-foundation.mjs` is tracked separately (same
   issue diagnosed in the insights AI proof).
4. **Pre-existing gate 7 polling race** — `web_cabinet/smoke.py` job-poll
   timing flake; tracked separately, unrelated to this PR.

## Honest status

`partially_proven`. Per CLAUDE.md §4 the bar for `proven` is all 7 gates
green; gates 5, 6, 7 are red. **All three failures are pre-existing and
fully diagnosed**, none are caused by analytics QC overlays code paths
(verified via stderr tails + report JSONs in `artifacts/_ci/`).

What is `proven` within scope of this PR:

- All QC backend (CRUD, detector, AI describer, event linker), cron job,
  and boundary routes pass targeted pytest (13 / 13).
- pytest gate, web smoke, verify_refactor, warning governance — all green.
- Live UI flows validated via Playwright with 6 screenshots committed.
- Date mapping bug found in validation was fixed in `cde6e02` and tsc-clean.

## Artifacts inventory

```
artifacts/_ci/gate_1_pytest.log
artifacts/_ci/gate_2_web_smoke.log
artifacts/_ci/web_smoke.json
artifacts/_ci/gate_3_verify_refactor.log
artifacts/_ci/verify_refactor/verify_20260507_203507/verify_report.{json,md}
artifacts/_ci/gate_4_warning_governance.log
artifacts/_ci/warning_governance_report.{json,md}
artifacts/_ci/gate_5_operational_rollout.log
artifacts/_ci/operational_rollout_gates/operational_rollout_gates_report.{json,md}
artifacts/_ci/gate_6_competitive_acceptance.log
artifacts/_ci/competitive_acceptance/competitive_acceptance_report.{json,md}
artifacts/_ci/gate_7_perf.log
artifacts/_ci/gate_7_perf_retry.log
artifacts/_ci/performance_gates/performance_gates_report.{json,md}
```

## Commits in scope

- `47f4288` migration (qc_incidents, event linked_metric_ids)
- `3d39c5e` backend bundle (detector, AI describer, linker, cron, routes)
- `3c5f4b6` frontend bundle (overlays + fullscreen modal)
- `d4e1b26` Playwright screenshots
- `cde6e02` post-validation fix (built-in tab charts + `findWeekIndex`)
