# P2-1 — Explicit 0/1-Knapsack Farm Context Compression

**Date:** 2026-05-09
**Source brief:** `docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md` §P2-1
**Thesis source:** §3.2.1, формула 3.5, табл. 3.2.1, гипотеза H1
**Predecessor:** existing `web_cabinet/ai/context.py:build_farm_context` (no budget enforcement)

## Goal

Replace silent unbounded context concatenation with an explicit greedy 0/1-knapsack compression by value-density (`weight / token_estimate`) so the operator-facing AI gets the highest-information-density segments first inside a fixed token budget. Confirms hypothesis H1: information value can be ranked and compressed without losing recommendation quality.

## Phase 1 — Compression module + math (1 commit)

**Files:** `web_cabinet/ai/context_compression.py` (new), `tests/web_cabinet/ai/test_context_compression.py` (new).

### Step 1: Add `Segment` dataclass

```python
@dataclasses.dataclass(frozen=True)
class Segment:
    name: str            # category label, e.g. "today_kpi", "attention_cow:3891", "recent_event:EV_3891_MAST"
    weight: float        # priority per §3.2.1 categories
    content: Any         # serialisable payload
    token_estimate: int  # cached for ordering
```

### Step 2: Token estimate (cyrillic-aware)

Per §3.2.1: `t_i ≈ |c_i| / 2.5 + 8`.

```python
def estimate_tokens(content: Any) -> int:
    """Cyrillic-aware token estimate per thesis §3.2.1."""
    text = json.dumps(content, ensure_ascii=False, default=str) if not isinstance(content, str) else content
    return max(1, math.ceil(len(text) / 2.5) + 8)
```

### Step 3: Greedy 0/1 knapsack

```python
def compress_farm_context(segments: list[Segment], *, budget: int = 3000) -> list[Segment]:
    """Greedy 0/1-knapsack by value-density (weight / token_estimate)."""
    ordered = sorted(segments, key=lambda s: s.weight / max(1, s.token_estimate), reverse=True)
    kept, used = [], 0
    for s in ordered:
        if used + s.token_estimate <= budget:
            kept.append(s)
            used += s.token_estimate
    return kept
```

### Step 4: Unit tests

- `test_estimate_tokens_cyrillic_formula` — string of length 50 cyrillic chars → 28 (math.ceil(50/2.5)+8 = 28).
- `test_compress_orders_by_density_first` — segments with `(weight=1.0, tokens=10)` and `(weight=0.5, tokens=10)` and budget=10 → only first kept.
- `test_compress_respects_budget` — sum(kept.tokens) ≤ budget.
- `test_compress_skips_oversized_segment_keeps_smaller` — single segment > budget never alone; second smaller segment fits.
- `test_compress_empty_input` → returns [].

### Step 5: Commit

```
feat(P2-1): explicit knapsack farm-context compression module
```

---

## Phase 2 — Category mapping + wire into build_farm_context (1 commit)

**Files:** `web_cabinet/ai/context.py` (edit), `web_cabinet/ai/context_compression.py` (extend), tests extended.

### Step 1: Category-weight table (per §3.2.1)

```python
CATEGORY_WEIGHTS = {
    "farm_summary":         1.0,
    "today_kpi":            1.0,
    "period_trends":        0.4,   # cohort/seasonal trend
    "active_insights":      0.4,
    "attention_cow":        0.9,   # one segment per cow
    "recent_event_7d":      0.7,   # ≤7 days old
    "recent_event_30d":     0.2,   # 7..30 days old
    "groups_summary":       0.5,
    "full_profile":         0.5,   # rare, only if include_cow_details
}
```

### Step 2: `_segment_farm_context(ctx, *, as_of) -> list[Segment]`

Splits the existing dict into segments:
- `farm_summary`, `today_kpi`, `period_trends`, `active_insights`, `groups_summary` → one segment each (cell-cohesive)
- `attention_cows: [{...}, ...]` → one segment per cow with `name="attention_cow:<animal_id>"`, `weight=0.9`
- `recent_events: [{...}, ...]` → split by age relative to `as_of`:
  - `event_date >= as_of − 7 days` → `weight=0.7`, name `"recent_event_7d:<event_id>"`
  - else → `weight=0.2`, name `"recent_event_30d:<event_id>"`
- `full_profiles: {cow_id: {...}}` → one segment per cow with `weight=0.5`

### Step 3: Reconstruct dict from kept segments

```python
def _reconstruct_ctx(kept: list[Segment]) -> dict:
    """Aggregate kept segments back into the dict shape build_farm_context returns."""
    out: dict[str, Any] = {}
    attention, events_7d, events_30d, profiles = [], [], [], {}
    for s in kept:
        if s.name.startswith("attention_cow:"):
            attention.append(s.content)
        elif s.name.startswith("recent_event_"):
            (events_7d if "7d:" in s.name else events_30d).append(s.content)
        elif s.name.startswith("full_profile:"):
            cow_id = s.name.split(":", 1)[1]
            profiles[cow_id] = s.content
        else:
            out[s.name] = s.content
    if attention: out["attention_cows"] = attention
    if events_7d or events_30d: out["recent_events"] = events_7d + events_30d
    if profiles: out["full_profiles"] = profiles
    return out
```

### Step 4: Wire into `build_farm_context`

Replace the final `ctx_text = json.dumps(...); ctx["token_count"] = ...` block with:

```python
segments = _segment_farm_context(ctx, as_of=as_of)
kept = compress_farm_context(segments, budget=context_token_budget)
compressed = _reconstruct_ctx(kept)
compressed["compression_stats"] = {
    "budget_tokens":   context_token_budget,
    "used_tokens":     sum(s.token_estimate for s in kept),
    "kept_segments":   len(kept),
    "dropped_segments": len(segments) - len(kept),
    "segments_by_category": _count_by_prefix(kept),
}
compressed["token_count"] = compressed["compression_stats"]["used_tokens"]
return compressed
```

Add a new kwarg `context_token_budget: int = 3000` to `build_farm_context`. Keep all existing kwargs intact.

### Step 5: Tests

- `test_segment_farm_context_splits_attention_per_cow` — ctx with 5 attention cows → 5 segments named `attention_cow:*`.
- `test_segment_farm_context_splits_events_by_age` — events at 5d, 10d, 25d → 1 weight=0.7, 2 weight=0.2.
- `test_reconstruct_preserves_dict_shape` — round-trip sanity.
- `test_build_farm_context_surfaces_compression_stats` — new key present, used_tokens ≤ budget.
- Verify all existing `build_farm_context` callers don't break (smoke).

### Step 6: Commit

```
feat(P2-1): wire knapsack compression into build_farm_context
```

---

## Phase 3 — Acceptance: H1 on demo farm (1 commit)

**Files:** `tests/web_cabinet/ai/test_context_compression.py` (extend).

### Step 1: H1 acceptance test

```python
def test_h1_acceptance_demo_farm_budget_3000():
    """Hypothesis H1: at budget=3000 on demo farm, retain:
       KPI 100%, attention ≥80%, events 7d ≥90%, build time <2s."""
    import time
    from pathlib import Path
    from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore
    store = DemoDataStore(base_dir=Path("data/demo/investor_v1"))
    farm_id = "demo-farm-v1"

    t0 = time.perf_counter()
    ctx = build_farm_context(farm_id, store=store, period_days=30, context_token_budget=3000)
    elapsed = time.perf_counter() - t0

    # Build uncompressed snapshot to compute expected coverage denominators
    full = build_farm_context(farm_id, store=store, period_days=30, context_token_budget=10**9)

    # KPI coverage = 100%: all top-level KPI cells present
    for k in ("farm_summary", "today_kpi"):
        assert k in ctx, f"missing top-priority key {k!r}"

    # Attention coverage
    full_attention = full.get("attention_cows", [])
    kept_attention = ctx.get("attention_cows", [])
    if full_attention:
        coverage = len(kept_attention) / len(full_attention)
        assert coverage >= 0.80, f"attention coverage {coverage:.0%} < 80%"

    # Recent-events 7d coverage
    today = datetime.date.fromisoformat(ctx["farm_summary"]["date_as_of"])
    def _is_7d(e):
        try:
            return (today - datetime.date.fromisoformat(str(e["event_date"])[:10])).days <= 7
        except Exception:
            return False
    full_7d = [e for e in full.get("recent_events", []) if _is_7d(e)]
    kept_7d = [e for e in ctx.get("recent_events", []) if _is_7d(e)]
    if full_7d:
        coverage = len(kept_7d) / len(full_7d)
        assert coverage >= 0.90, f"events_7d coverage {coverage:.0%} < 90%"

    # Performance: <2s
    assert elapsed < 2.0, f"build took {elapsed:.2f}s ≥ 2.0s"

    # Compression stats sanity
    cs = ctx["compression_stats"]
    assert cs["used_tokens"] <= cs["budget_tokens"]
    assert cs["kept_segments"] >= 5  # at minimum farm_summary + today_kpi + a few others
```

### Step 2: Calibrate if acceptance fails

If KPI/attention/events coverage falls short under budget=3000, calibrate ONE of:
- raise weight of the underperforming category (e.g. attention 0.9 → 1.0)
- bump budget per §3.2.1 (table 3.2.1 may sanction alternate values)

Document any calibration in the proof file with rationale citing §3.2.1.

### Step 3: Commit

```
feat(P2-1): H1 acceptance test on demo farm (KPI 100%, attn ≥80%, events 7d ≥90%)
```

---

## Phase 4 — Docs + CI gates + execution proof (1 commit)

- [ ] Update `docs/public_interfaces.md` if `build_farm_context` adds public kwargs (it does — `context_token_budget`).
- [ ] Run all 7 CI gates per CLAUDE.md §4.
- [ ] Write `docs/iterations/T34-P2-1_execution_proof.md` mirroring T34-P1-2c proof: scope, commits, acceptance table, before/after snapshot of `compression_stats` for demo farm at budget=3000 vs unlimited, gate run table, honest status `proven`.
- [ ] Final commit + push.

---

## Acceptance criteria (plan-level)

- [ ] All Phase 1–3 unit tests pass
- [ ] `compress_farm_context()` greedy by `weight/token_estimate` desc, ≤ budget
- [ ] §3.2.1 weights enforced: 1.0/0.9/0.7/0.5/0.4/0.2
- [ ] Token estimator: `ceil(|c|/2.5) + 8`
- [ ] H1 acceptance on demo farm: KPI 100%, attn ≥80%, events 7d ≥90%, time <2s
- [ ] All 7 CI gates green
- [ ] Honest status: `proven`

## Out of scope

- Replacing token estimate with `tiktoken` or live Anthropic counter (deferred — formula 3.5 is the thesis source-of-truth).
- Dynamic per-call budget tuning (out — fixed default 3000 with kwarg override).
- Bridge-mode `_build_bridge_context` compression (deferred — bridge mode not deployed in current build, see ai-ask-farm-tool-loop flowchart Gap 1).
- Frontend UI surfacing `compression_stats`.
