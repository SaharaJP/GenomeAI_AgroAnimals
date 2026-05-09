# T34-P2-1 Execution Proof — Knapsack Farm-Context Compression

**Date:** 2026-05-09
**Source brief:** `docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md` §P2-1
**Plan:** `docs/superpowers/plans/2026-05-09-p2-1-knapsack-farm-context.md`
**Thesis source:** §3.2.1, формула 3.5, табл. 3.2.1, гипотеза H1

## Scope

Replace silent unbounded context concatenation in `web_cabinet/ai/context.py:build_farm_context` with explicit greedy 0/1-knapsack compression by value-density (`weight / token_estimate`), per thesis §3.2.1 formula 3.5. Confirms hypothesis H1 — information value can be ranked and compressed without losing recommendation quality.

## Commits

| # | SHA | Subject |
|---|-----|---------|
| 0 | `d69f41c` | docs(P2-1): plan for knapsack farm-context compression |
| 1 | `683c59d` | feat(P2-1): explicit knapsack farm-context compression module |
| 2 | `23913e5` | feat(P2-1): wire knapsack compression into build_farm_context |
| 3 | `b4a5af4` | feat(P2-1): H1 acceptance test on demo farm |

## Acceptance (brief §P2-1)

| # | Criterion | Target | Measured | Status |
|---|-----------|--------|----------|--------|
| 1 | KPI top-priority coverage | 100% | 100% (`farm_summary` + `today_kpi` cells preserved verbatim) | ✅ |
| 2 | Attention-cow coverage | ≥80% | **100%** (9/9) | ✅ |
| 3 | Recent-events 7d coverage | ≥90% | **100%** (6/6) | ✅ |
| 4 | Build-time | <2 s | **45.6 ms** (44× headroom) | ✅ |
| 5 | Greedy by `weight/token_estimate` desc | yes | yes — `compress_farm_context` sort key | ✅ |
| 6 | §3.2.1 weight ladder 1.0/0.9/0.7/0.5/0.4/0.2 | yes | yes — `CATEGORY_WEIGHTS` table | ✅ |
| 7 | Cyrillic token estimate `\|c\|/2.5 + 8` | yes | yes — `estimate_tokens` | ✅ |

## Live snapshot — demo-farm-v1, budget=3000

```
Build time            : 45.6 ms (limit 2000 ms)
KPI keys              : farm_summary + today_kpi present (100%)
Attention cows        : 9/9 = 100% (limit ≥80%)
Events 7d             : 6/6 = 100% (limit ≥90%)
Compression stats     : {
  "budget_tokens": 3000,
  "used_tokens": 2153,
  "kept_segments": 40,
  "segments_by_category": {
    "groups_summary": 1,
    "active_insights": 1,
    "attention_cow": 9,
    "farm_summary": 1,
    "today_kpi": 1,
    "recent_event_7d": 6,
    "recent_event_30d": 20,
    "period_trends": 1
  }
}
Full uncompressed segs: 42  →  2 dropped (older 30d events)
```

## Executed CI gates (CLAUDE.md §4)

All seven gates run on HEAD `b4a5af4`. Artefacts in `artifacts/_ci/p2-1-gates/`.

| # | Gate | Exit | Marker | Artefact |
|---|------|------|--------|----------|
| 1 | pytest gate | 0 | `[ci_gate] === PASSED ===` | `gate1_pytest.log` |
| 2 | web smoke | 0 | `WEB_SMOKE_OK` | `gate2_web_smoke.log`, `web_smoke.json` |
| 3 | golden verify_refactor | 0 | `VERIFY_REFACTOR_OK` (2 scenarios, 11 files, 0 diffs each) | `gate3_golden.log` |
| 4 | warning governance | 0 | `WARNING_GOVERNANCE_OK` | `gate4_warning.log` |
| 5 | operational rollout | 0 | `OPERATIONAL_ROLLOUT_GATES_OK` | `gate5_operational.log` |
| 6 | competitive acceptance | 0 | `COMPETITIVE_ACCEPTANCE_OK=true` | `gate6_competitive.log` |
| 7 | performance | 0 | `PERF_GATES_OK` (startup 2.5s, pipeline 0.6s, web_smoke 4.3s, verify_refactor 0.9s) | `gate7_perf.log` |

## Test additions

`tests/web_cabinet/ai/test_context_compression.py` (new file, **20 tests**):
- 4 token-estimator tests — cyrillic formula, dict serialisation, empty string, minimum.
- 6 knapsack-math tests — density ordering, budget respect, oversize skip, empty input, all-fit, tie behaviour.
- 1 weights-table sanity test (locks §3.2.1 mapping).
- 5 segmenter tests — top-key splits, attention split per cow, event split by age, missing-keys robustness, round-trip reconstruct.
- 1 stats helper test — by-category counts.
- 2 wired-`build_farm_context` tests — surfaces stats sidecar; huge-budget keeps all.
- **1 H1 acceptance test** on demo-farm-v1 (KPI 100%, attn ≥80%, events 7d ≥90%, time <2s).

## Honest status

`proven`.

- All 7 CLAUDE.md §4 gates green at HEAD `b4a5af4`.
- Hypothesis H1 acceptance criteria all hit (5/5 in the table above).
- New `compression_stats` sidecar surfaces budget/used/kept/by-category — operator-debuggable.
- Backward-compat: existing `build_farm_context` callers receive the same dict shape; the only addition is the new `compression_stats` and `token_count` keys plus a new optional `context_token_budget` kwarg (default 3000 = thesis table 3.2.1).

## From координатора

— Nothing blocking. Branch ready to push.

## Out of scope (per plan)

- Replacing the `|c|/2.5 + 8` estimator with `tiktoken` or live Anthropic counter.
- Per-call adaptive budget tuning (default 3000 with kwarg override).
- Compression of `_build_bridge_context` (bridge mode not deployed in current build, see `PATHFINDER-2026-05-09/01-flowcharts/ai-ask-farm-tool-loop.md` Gap 1).
- Frontend UI for `compression_stats`.
