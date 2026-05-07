# T34 — Data Upload via FAB: execution proof

## Scope

Add a 4-step wizard launched from the FAB menu for uploading CSV/XLSX
files into 4 dm_* tables (milkings, health_events, animals, feed_rations).
TYPE_REGISTRY drives templates + validation + INSERT.

Plan: docs/superpowers/plans/2026-05-07-data-upload-fab.md
Spec: docs/superpowers/specs/2026-05-07-data-upload-fab-design.md

## Executed checks

### CLAUDE.md §4 — 7 CI gates

| # | Gate | Result | Exit | Artifact |
|---|------|--------|------|----------|
| 1 | pytest (`scripts/run_ci_gate.sh`)            | green | 0 | `artifacts/_ci/gate_1_pytest.log` |
| 2 | web smoke                                    | green | 0 | `artifacts/_ci/web_smoke.json`, `gate_2_web_smoke.log` |
| 3 | verify_refactor                              | green | 0 | `artifacts/_ci/gate_3_verify_refactor.log` |
| 4 | warning governance                           | green | 0 | `artifacts/_ci/gate_4_warning_governance.log` |
| 5 | operational rollout                          | red   | 2 | `artifacts/_ci/gate_5_operational_rollout.log` |
| 6 | competitive acceptance                       | red   | 2 | `artifacts/_ci/gate_6_competitive_acceptance.log` |
| 7 | performance                                  | green | 0 | `artifacts/_ci/gate_7_perf.log` |

Net: 5/7 green.

Gate 5 sub-results:
- compile_daily_pages ok=true
- role_scenarios ok=true
- mobile_views ok=true
- worklists_profiles_reports ok=false   <-- failing sub-gate
- rollout_diagnostics ok=true

Gate 6 sub-results:
- daily_operations: not_ready
- reproduction: ready_for_manual_signoff
- vet: ready_for_manual_signoff
- reports_worklists: not_ready
- mobile: not_ready
- migration: ready_for_manual_signoff

### Targeted uploads pytest

`pytest tests/test_uploads_template.py tests/test_uploads_parse.py
tests/test_uploads_validation.py tests/test_uploads_commit.py` →
**28 passed, 30 warnings in 1.05s**.

Coverage:
- `test_uploads_template.py` — list-types + per-type schema/template (CSV+XLSX)
- `test_uploads_parse.py` — preview parsing (CSV, XLSX, header diffs, dup detection)
- `test_uploads_validation.py` — TYPE_REGISTRY validators (required, types, ranges, FK)
- `test_uploads_commit.py` — token lifecycle, idempotency (consumed-once), DB INSERT

### Live UI validation

Playwright screenshots committed in `b2edab6` (repo-root PNGs):
- `data-upload-fab.png` — FAB menu shows 3 items (новый «Загрузить данные»)
- `data-upload-step1.png` — Step 1 with 4 type cards
- `data-upload-template.png` — Step 2: column list + CSV/XLSX download buttons + dropzone
- `data-upload-preview.png` — Step 3: 1 valid / 0 duplicates / 0 errors
- `data-upload-success.png` — wizard closed after commit

End-to-end proof: PLAYW_A1 milkings row inserted (visible in
dm_milkings_daily) then cleaned up.

## Failure analysis (gates 5/6)

Same root cause as prior T34 proofs: pre-existing regression from
commit `7b08924` where `web_app/scripts/validate-foundation.mjs:60`
asserts an English string that was Russified across UI surfaces.
This regression is **NOT introduced by the data-upload-fab feature**;
it was already red on `main` before this PR's first commit (`8bfd820`).

The failing sub-gates (`worklists_profiles_reports`,
`daily_operations`, `reports_worklists`, `mobile`) all transit through
the foundation-validation step that fails on the Russian-string
assertion.

## Net result

5/7 CI gates green. Gates 5/6 red due to pre-existing Russian
translation regression in `validate-foundation.mjs`, untouched by
this PR. Spec acceptance criteria 1-9 verified by:
- Targeted pytest (28/28 passing)
- Playwright live UI validation (5 screenshots)
- Live DB roundtrip via PLAYW_A1 fixture in dm_milkings_daily

## Honest status

`partially_proven`.

Reason: 5/7 gates green; 2 red gates are pre-existing infra failures
unrelated to the upload feature. Feature itself is fully validated
via targeted pytest + Playwright + live DB roundtrip, but per
CLAUDE.md §4 ("Без зелёных 7 гейтов статус выше `partially_proven`
выставлять нельзя") cannot claim `proven`.
