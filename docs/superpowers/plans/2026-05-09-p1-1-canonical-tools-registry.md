# P1-1 Canonical Tools Registry & Agent Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `web_cabinet/ai/tools.py` so the 7 canonical tools from thesis §3.1.4 (Table 3.1.4) are present in code with the exact names, and integrate them into a real agent loop on `POST /api/ai/ask-farm` so model-driven tool use works end-to-end.

**Architecture:**
- Rename 3 existing tools to canonical names (`get_cow_history → get_animal_profile`, `get_group_metrics → get_kpi_summary`, `search_events → search_events_timeline`); preserve 3 production-extras as-is.
- Add 4 new canonical tools (`analyze_event_impact`, `find_attention_cows`, `calculate_cull_npv` (stub for P1-2), `forecast_milk_yield`).
- New helper `AnthropicClient.tool_call_loop()` runs the standard Anthropic agent loop (model → tool_use → execute → tool_result → model → final text), bounded by `max_iterations` to prevent runaway calls.
- `ask_farm._stream_live` calls `tool_call_loop` first, emits per-tool SSE `tool_used` events, then streams the final assistant text token-by-token (preserves current frontend SSE contract).

**Tech Stack:** Python 3.12, FastAPI, anthropic SDK, pandas, pytest.

**Spec:** `docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md` §2 P1-1 + §3.1.4 of dissertation.

**Commit strategy (CLAUDE.md §3):** 9 commits — `feat(P1-1)` per phase + `docs(P1-1)` for the proof file. No migrations, no golden updates.

**Pragmatic notes:**
1. Brief estimates 4–6h; realistic budget is ~9h because the brief assumes an agent loop that does not currently exist (`ask_farm.py` uses pure text streaming via `client.astream`).
2. `calculate_cull_npv` is a **stub for P1-1**: it wraps existing `_exec_economics_snapshot(cow_id=animal_id)`. Full NPV (NPV_keep vs NPV_cull, sensitivity) is **P1-2 scope**.
3. `forecast_milk_yield` uses minimal linear regression on DIM (per brief: "минимум — линейная регрессия от DIM, без сложной модели").
4. Brief permits extending `get_animal_profile` output ("можно расширить") — **deferred to P1-1b**; Phase 1 is pure rename.
5. No public_interfaces.json change: tool names are not in the contract surface (verified via grep on 2026-05-09).

---

## Phase 1 — Tool registry rename + new definitions (1 commit)

### Task 1.1: Update existing test for renamed tool names

**Files:**
- Modify: `tests/web_cabinet/ai/test_tools.py`

- [ ] **Step 1: Read current test to understand fixtures**

Run: `head -100 tests/web_cabinet/ai/test_tools.py`

- [ ] **Step 2: Replace old names with canonical names in test list**

In `tests/web_cabinet/ai/test_tools.py`, replace these strings (every occurrence):
- `"get_cow_history"` → `"get_animal_profile"`
- `"get_group_metrics"` → `"get_kpi_summary"`
- `"search_events"` → `"search_events_timeline"`

(Use `Edit` with `replace_all=true` on each, three edits total.)

- [ ] **Step 3: Run test — must FAIL with `unknown tool` errors**

Run: `pytest tests/web_cabinet/ai/test_tools.py -x -q 2>&1 | tail -20`
Expected: FAIL — executor map still has old keys, dispatcher returns `{"error": "unknown tool: get_animal_profile"}`.

### Task 1.2: Rename tool dicts and executor map keys in `tools.py`

**Files:**
- Modify: `web_cabinet/ai/tools.py`

- [ ] **Step 1: Rename 3 tool definition dicts (`name` field only — bodies unchanged per brief)**

```python
# Line 14: COW_HISTORY_TOOL — change "name"
"name": "get_animal_profile",

# Line 34: GROUP_METRICS_TOOL — change "name"
"name": "get_kpi_summary",

# Line 59: EVENT_SEARCH_TOOL — change "name"
"name": "search_events_timeline",
```

- [ ] **Step 2: Update dispatcher map (line 229–237)**

Replace:
```python
handlers = {
    "get_cow_history": _exec_cow_history,
    "get_group_metrics": _exec_group_metrics,
    "search_events": _exec_search_events,
    ...
}
```
With:
```python
handlers = {
    "get_animal_profile": _exec_cow_history,
    "get_kpi_summary": _exec_group_metrics,
    "search_events_timeline": _exec_search_events,
    "get_treatment_records": _exec_treatment_records,
    "get_reproduction_status": _exec_reproduction_status,
    "get_milk_quality_trend": _exec_milk_quality_trend,
    "get_economics_snapshot": _exec_economics_snapshot,
}
```
(Internal `_exec_*` function names stay — only public tool names change.)

- [ ] **Step 3: Run test — should PASS**

Run: `pytest tests/web_cabinet/ai/test_tools.py -x -q 2>&1 | tail -10`
Expected: All renamed-tool tests PASS.

### Task 1.3: Add 4 new tool definition dicts (executors stub-raise)

**Files:**
- Modify: `web_cabinet/ai/tools.py`

- [ ] **Step 1: Append 4 tool definitions before `ALL_TOOLS = [...]` (line 179)**

```python
ANIMAL_PROFILE_TOOL = COW_HISTORY_TOOL  # alias for clarity in registry list
KPI_SUMMARY_TOOL = GROUP_METRICS_TOOL
SEARCH_EVENTS_TIMELINE_TOOL = EVENT_SEARCH_TOOL

ANALYZE_EVENT_IMPACT_TOOL = {
    "name": "analyze_event_impact",
    "description": (
        "Запустить импакт-анализ влияния события (смена рациона, лечение, "
        "перевод группы) на KPI стада. Возвращает баланс/наблюдение и "
        "доверительный интервал."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "ID события для анализа"},
            "kpi": {
                "type": "string",
                "enum": ["milk_kg", "scc", "fat_pct", "protein_pct"],
                "default": "milk_kg",
                "description": "KPI для импакт-анализа",
            },
            "window_days": {
                "type": "integer",
                "default": 14,
                "description": "Окно (дней) до/после события",
            },
        },
        "required": ["event_id"],
    },
}

FIND_ATTENTION_COWS_TOOL = {
    "name": "find_attention_cows",
    "description": (
        "Топ-N коров «под наблюдением» по комбинированному скору: высокий SCC, "
        "падение надоя, активные лечения, отклонения BCS. Используй когда оператор "
        "спрашивает «кто требует внимания» / «кого посмотреть сегодня»."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "threshold_count": {
                "type": "integer",
                "default": 10,
                "description": "Сколько коров вернуть",
            },
        },
    },
}

CALCULATE_CULL_NPV_TOOL = {
    "name": "calculate_cull_npv",
    "description": (
        "Расчёт NPV для выбраковки конкретной коровы: NPV_keep, NPV_cull, "
        "рекомендация. P1-1 — обёртка над economics_snapshot; полный NPV приходит в P1-2."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "animal_id": {"type": "string", "description": "ID коровы"},
        },
        "required": ["animal_id"],
    },
}

FORECAST_MILK_YIELD_TOOL = {
    "name": "forecast_milk_yield",
    "description": (
        "Прогноз надоя на 7–30 дней вперёд на уровне коровы или группы. "
        "Линейная регрессия по DIM."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "animal_id": {"type": "string", "description": "ID коровы (или null для группы)"},
            "group_id": {"type": "string", "description": "ID группы (или null для коровы)"},
            "horizon_days": {
                "type": "integer",
                "default": 7,
                "description": "Горизонт прогноза (7–30)",
            },
        },
    },
}
```

- [ ] **Step 2: Replace `ALL_TOOLS = [...]` with canonical + extras structure**

```python
# Канонические 7 инструментов соответствуют разделу 3.1.4 ВКР.
CANONICAL_TOOLS = [
    ANIMAL_PROFILE_TOOL,
    ANALYZE_EVENT_IMPACT_TOOL,
    FORECAST_MILK_YIELD_TOOL,
    CALCULATE_CULL_NPV_TOOL,
    FIND_ATTENTION_COWS_TOOL,
    KPI_SUMMARY_TOOL,
    SEARCH_EVENTS_TIMELINE_TOOL,
]
# Дополнительные 3 — production-расширения, не упоминаются в дипломе.
EXTRA_TOOLS = [
    TREATMENT_TOOL,
    REPRODUCTION_TOOL,
    MILK_QUALITY_TOOL,
]
ALL_TOOLS = CANONICAL_TOOLS + EXTRA_TOOLS  # 10 total
```

- [ ] **Step 3: Add stub executors in dispatcher (raise NotImplementedError so Phase 2 fails-loud)**

In the `handlers` dict (now ~line 237), add:
```python
"analyze_event_impact": _exec_analyze_event_impact,
"find_attention_cows": _exec_find_attention_cows,
"calculate_cull_npv": _exec_calculate_cull_npv,
"forecast_milk_yield": _exec_forecast_milk_yield,
```

And append at end of file:
```python
def _exec_analyze_event_impact(inp: dict, store: Any) -> dict:
    raise NotImplementedError("P1-1 task 2.1")

def _exec_find_attention_cows(inp: dict, store: Any) -> dict:
    raise NotImplementedError("P1-1 task 2.2")

def _exec_calculate_cull_npv(inp: dict, store: Any) -> dict:
    raise NotImplementedError("P1-1 task 2.3")

def _exec_forecast_milk_yield(inp: dict, store: Any) -> dict:
    raise NotImplementedError("P1-1 task 2.4")
```

- [ ] **Step 4: Existing tests still pass (smoke)**

Run: `pytest tests/web_cabinet/ai/test_tools.py -x -q 2>&1 | tail -5`
Expected: PASS (the 4 new executors aren't called by existing tests).

- [ ] **Step 5: Commit Phase 1**

```bash
git add web_cabinet/ai/tools.py tests/web_cabinet/ai/test_tools.py
git commit -m "$(cat <<'EOF'
feat(P1-1): canonical tool names per thesis §3.1.4

- Rename get_cow_history → get_animal_profile
- Rename get_group_metrics → get_kpi_summary
- Rename search_events → search_events_timeline
- Add stub definitions for analyze_event_impact, find_attention_cows,
  calculate_cull_npv, forecast_milk_yield (executors NotImplementedError
  until Phase 2)
- Split ALL_TOOLS into CANONICAL_TOOLS + EXTRA_TOOLS

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Implement 4 new tool executors (4 commits)

### Task 2.1: `_exec_analyze_event_impact`

**Files:**
- Modify: `web_cabinet/ai/tools.py`
- Modify: `web_cabinet/ai/endpoints/impact_narrative.py` (extract shared function)
- Test: `tests/web_cabinet/ai/test_tools_canonical_set.py` (new file, partial — final form in Phase 5)

- [ ] **Step 1: Read current impact_narrative.py to identify pure function**

Run: `grep -n 'def \|async def ' web_cabinet/ai/endpoints/impact_narrative.py`

Identify the function that computes impact (likely `compute_event_impact(event_id, kpi, window_days)` or inline logic in route handler). If only inline, extract.

- [ ] **Step 2: Write failing test**

Create `tests/web_cabinet/ai/test_tools_canonical_set.py`:
```python
"""Acceptance: 7 canonical tools per thesis §3.1.4 work on demo store."""
from __future__ import annotations
import pytest
from web_cabinet.ai.tools import CANONICAL_TOOLS, EXTRA_TOOLS, ALL_TOOLS, execute_tool


def test_canonical_set_has_7_tools():
    names = {t["name"] for t in CANONICAL_TOOLS}
    assert names == {
        "get_animal_profile",
        "analyze_event_impact",
        "forecast_milk_yield",
        "calculate_cull_npv",
        "find_attention_cows",
        "get_kpi_summary",
        "search_events_timeline",
    }, f"canonical drift: {names}"


def test_all_tools_total_10():
    assert len(ALL_TOOLS) == 10
    assert len(EXTRA_TOOLS) == 3


def test_analyze_event_impact_smoke(rich_store):
    # Pick any known event_id from the demo store fixture
    events = rich_store.events_for_farm()
    assert events, "demo store has no events"
    eid = str(events[0].get("event_id") or events[0].get("id"))
    result = execute_tool(
        "analyze_event_impact",
        {"event_id": eid, "kpi": "milk_kg", "window_days": 14},
        rich_store,
    )
    assert "kpi" in result
    assert "delta" in result or "impact" in result
    assert "evidence_chips" in result
```

- [ ] **Step 3: Run test — must FAIL with NotImplementedError**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_analyze_event_impact_smoke -x 2>&1 | tail -15`
Expected: FAIL with `NotImplementedError: P1-1 task 2.1`.

- [ ] **Step 4: Extract shared compute function**

In `web_cabinet/ai/endpoints/impact_narrative.py`: refactor route to call a new `compute_event_impact(event_id, kpi, window_days, store) -> dict` (return dict with `kpi`, `delta`, `confidence_lo`, `confidence_hi`, `n_before`, `n_after`, `evidence_chips`). Route handler stays the public surface.

- [ ] **Step 5: Implement executor**

In `web_cabinet/ai/tools.py`, replace the stub with:
```python
def _exec_analyze_event_impact(inp: dict, store: Any) -> dict:
    from .endpoints.impact_narrative import compute_event_impact
    event_id = str(inp["event_id"])
    kpi = str(inp.get("kpi", "milk_kg"))
    window_days = int(inp.get("window_days", 14))
    result = compute_event_impact(event_id, kpi, window_days, store)
    return _truncate(result, "analyze_event_impact")
```

- [ ] **Step 6: Run test — must PASS**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_analyze_event_impact_smoke -x 2>&1 | tail -10`
Expected: PASS.

- [ ] **Step 7: Run existing impact_narrative tests — no regressions**

Run: `pytest tests/web_cabinet/ai/ -k 'impact' -x -q 2>&1 | tail -5`
Expected: All green.

- [ ] **Step 8: Commit**

```bash
git add web_cabinet/ai/tools.py web_cabinet/ai/endpoints/impact_narrative.py tests/web_cabinet/ai/test_tools_canonical_set.py
git commit -m "feat(P1-1): _exec_analyze_event_impact via shared compute_event_impact

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: `_exec_find_attention_cows`

**Files:**
- Modify: `web_cabinet/ai/tools.py`
- Modify: `tests/web_cabinet/ai/test_tools_canonical_set.py`

- [ ] **Step 1: Add failing test**

Append to `tests/web_cabinet/ai/test_tools_canonical_set.py`:
```python
def test_find_attention_cows_smoke(rich_store):
    result = execute_tool("find_attention_cows", {"threshold_count": 5}, rich_store)
    assert "cows" in result
    assert isinstance(result["cows"], list)
    assert len(result["cows"]) <= 5
    if result["cows"]:
        cow = result["cows"][0]
        assert "cow_id" in cow
        assert "score" in cow
        assert "reasons" in cow
    assert "evidence_chips" in result
```

- [ ] **Step 2: Run test — FAIL with NotImplementedError**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_find_attention_cows_smoke -x 2>&1 | tail -10`

- [ ] **Step 3: Implement executor**

```python
def _exec_find_attention_cows(inp: dict, store: Any) -> dict:
    n = int(inp.get("threshold_count", 10))
    cows = store.list_cows() if hasattr(store, "list_cows") else []
    scored = []
    for c in cows:
        cid = str(c.get("cow_id") or c.get("id"))
        score = 0.0
        reasons = []
        scc = float(c.get("scc", 0) or 0)
        if scc > 200_000:
            score += min(scc / 200_000.0, 5.0)
            reasons.append(f"SCC {int(scc):,}")
        bcs = float(c.get("bcs", 3.0) or 3.0)
        if bcs < 2.5 or bcs > 4.0:
            score += 1.0
            reasons.append(f"BCS {bcs}")
        if c.get("attention", False):
            score += 2.0
            reasons.append("flagged: attention")
        if score > 0:
            scored.append({"cow_id": cid, "score": round(score, 2), "reasons": reasons})
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:n]
    return {
        "cows": top,
        "total_scored": len(scored),
        "evidence_chips": [{"type": "cow", "id": c["cow_id"]} for c in top],
    }
```

- [ ] **Step 4: PASS check**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_find_attention_cows_smoke -x 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web_cabinet/ai/tools.py tests/web_cabinet/ai/test_tools_canonical_set.py
git commit -m "feat(P1-1): _exec_find_attention_cows scoring + TOP-N

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.3: `_exec_calculate_cull_npv` (P1-1 stub)

**Files:**
- Modify: `web_cabinet/ai/tools.py`
- Modify: `tests/web_cabinet/ai/test_tools_canonical_set.py`

- [ ] **Step 1: Add failing test**

```python
def test_calculate_cull_npv_stub(rich_store):
    # Stub semantics for P1-1: returns NPV snapshot for a cow.
    # Full keep-vs-cull comparison is P1-2.
    cow = next(iter(rich_store.list_cows()))
    cid = str(cow.get("cow_id") or cow.get("id"))
    result = execute_tool("calculate_cull_npv", {"animal_id": cid}, rich_store)
    assert "animal_id" in result
    assert "npv_snapshot" in result
    assert result.get("p1_1_stub") is True, "must declare itself a stub"
    assert "evidence_chips" in result
```

- [ ] **Step 2: Run test — FAIL**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_calculate_cull_npv_stub -x 2>&1 | tail -5`

- [ ] **Step 3: Implement stub executor**

```python
def _exec_calculate_cull_npv(inp: dict, store: Any) -> dict:
    """P1-1 stub. Full NPV_keep vs NPV_cull is P1-2 scope."""
    animal_id = str(inp["animal_id"])
    snapshot = _exec_economics_snapshot({"cow_id": animal_id}, store)
    return {
        "animal_id": animal_id,
        "npv_snapshot": snapshot,
        "p1_1_stub": True,
        "note": "Полная NPV_keep vs NPV_cull модель появится в P1-2.",
        "evidence_chips": [{"type": "cow", "id": animal_id}],
    }
```

- [ ] **Step 4: PASS check + commit**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_calculate_cull_npv_stub -x 2>&1 | tail -5`

```bash
git add web_cabinet/ai/tools.py tests/web_cabinet/ai/test_tools_canonical_set.py
git commit -m "feat(P1-1): _exec_calculate_cull_npv stub wraps economics_snapshot (P1-2 fills it)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.4: `_exec_forecast_milk_yield`

**Files:**
- Modify: `web_cabinet/ai/tools.py`
- Modify: `tests/web_cabinet/ai/test_tools_canonical_set.py`

- [ ] **Step 1: Add failing test**

```python
def test_forecast_milk_yield_animal(rich_store):
    cow = next(iter(rich_store.list_cows()))
    cid = str(cow.get("cow_id") or cow.get("id"))
    result = execute_tool(
        "forecast_milk_yield",
        {"animal_id": cid, "horizon_days": 7},
        rich_store,
    )
    assert "horizon_days" in result
    assert "forecast" in result
    assert isinstance(result["forecast"], list)
    assert len(result["forecast"]) == 7
    assert "method" in result and result["method"] == "linear_regression_dim"
    assert "evidence_chips" in result
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement (linear regression on DIM)**

```python
def _exec_forecast_milk_yield(inp: dict, store: Any) -> dict:
    animal_id = inp.get("animal_id")
    group_id = inp.get("group_id")
    horizon = max(7, min(30, int(inp.get("horizon_days", 7))))
    if not animal_id and not group_id:
        return {"error": "either animal_id or group_id required"}
    df = store.milk_df_for_cow(animal_id) if animal_id else store.milk_df_for_group(group_id)
    if df is None or df.empty or "dim" not in df.columns or "milk_kg" not in df.columns:
        return {"error": "insufficient data", "horizon_days": horizon, "forecast": []}
    import numpy as np
    x = df["dim"].astype(float).to_numpy()
    y = df["milk_kg"].astype(float).to_numpy()
    if len(x) < 3:
        return {"error": "need >=3 points", "horizon_days": horizon, "forecast": []}
    slope, intercept = np.polyfit(x, y, 1)
    last_dim = float(x.max())
    forecast = [
        {"dim": int(last_dim + d), "milk_kg": round(float(slope * (last_dim + d) + intercept), 2)}
        for d in range(1, horizon + 1)
    ]
    chips = [{"type": "cow" if animal_id else "group", "id": str(animal_id or group_id)}]
    return {
        "animal_id": animal_id,
        "group_id": group_id,
        "horizon_days": horizon,
        "forecast": forecast,
        "method": "linear_regression_dim",
        "slope_per_day": round(float(slope), 4),
        "evidence_chips": chips,
    }
```

If `store` lacks `milk_df_for_cow` / `milk_df_for_group`, add those helpers in the demo store (small, mechanical) — note the location and add inline.

- [ ] **Step 4: PASS check + commit**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py::test_forecast_milk_yield_animal -x 2>&1 | tail -5`

```bash
git add web_cabinet/ai/tools.py tests/web_cabinet/ai/test_tools_canonical_set.py
git commit -m "feat(P1-1): _exec_forecast_milk_yield linear regression on DIM

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Agent loop helper in `client.py` (1 commit)

### Task 3.1: TDD a bounded tool-use loop helper

**Files:**
- Modify: `web_cabinet/ai/client.py`
- Test: `tests/web_cabinet/ai/test_tool_call_loop.py` (new)

- [ ] **Step 1: Read existing `tool_call` (client.py:343–392)** — already done in plan research.

- [ ] **Step 2: Write failing test using stub Anthropic client**

Create `tests/web_cabinet/ai/test_tool_call_loop.py`:
```python
"""Test bounded agent loop: tool_call_loop runs model→tool→result→model until stop."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from web_cabinet.ai.client import AnthropicClient


class _StubBlock:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.type = kw.get("type", "text")


def _make_response(*, stop_reason: str, blocks: list, model: str = "claude-opus-4-7"):
    r = MagicMock()
    r.model = model
    r.content = blocks
    r.stop_reason = stop_reason
    r.usage.input_tokens = 100
    r.usage.output_tokens = 50
    r.usage.cache_creation_input_tokens = 0
    r.usage.cache_read_input_tokens = 0
    return r


def test_tool_call_loop_no_tools_used(monkeypatch):
    """Model returns end_turn directly without any tool_use → loop exits with text."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    fake.messages.create.return_value = _make_response(
        stop_reason="end_turn",
        blocks=[_StubBlock(type="text", text="Привет")],
    )
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    result = client.tool_call_loop(
        user_message="Привет",
        tools=[],
        executor=lambda name, inp: {"unused": True},
    )
    assert result.content == "Привет"
    assert result.tools_used == []


def test_tool_call_loop_one_tool_then_stop(monkeypatch):
    """Model uses one tool, gets result, returns final text."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    # First response: tool_use
    first = _make_response(
        stop_reason="tool_use",
        blocks=[_StubBlock(
            type="tool_use",
            id="tool_1",
            name="get_animal_profile",
            input={"cow_id": "Star"},
        )],
    )
    # Second response: end_turn with text
    second = _make_response(
        stop_reason="end_turn",
        blocks=[_StubBlock(type="text", text="SCC 180 тыс., надой 28 кг.")],
    )
    fake.messages.create.side_effect = [first, second]
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    captured = []
    def executor(name, inp):
        captured.append((name, inp))
        return {"scc": 180000, "milk_kg": 28}

    result = client.tool_call_loop(
        user_message="карточку Звёздочки",
        tools=[{"name": "get_animal_profile", "input_schema": {"type": "object", "properties": {}}}],
        executor=executor,
    )
    assert result.content == "SCC 180 тыс., надой 28 кг."
    assert len(result.tools_used) == 1
    assert result.tools_used[0]["name"] == "get_animal_profile"
    assert captured == [("get_animal_profile", {"cow_id": "Star"})]


def test_tool_call_loop_max_iterations(monkeypatch):
    """Loop bounds iterations to prevent runaway."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    fake.messages.create.return_value = _make_response(
        stop_reason="tool_use",
        blocks=[_StubBlock(type="tool_use", id="t", name="x", input={})],
    )
    monkeypatch.setattr(client, "_get_client", lambda: fake)
    with pytest.raises(RuntimeError, match="max_iterations"):
        client.tool_call_loop(
            user_message="loop",
            tools=[{"name": "x", "input_schema": {"type": "object"}}],
            executor=lambda n, i: {},
            max_iterations=2,
        )
```

- [ ] **Step 3: Run — FAIL (`tool_call_loop` doesn't exist)**

Run: `pytest tests/web_cabinet/ai/test_tool_call_loop.py -x 2>&1 | tail -10`

- [ ] **Step 4: Implement `tool_call_loop` in `client.py`**

Add to `AnthropicClient` class (sync, mirrors the existing `generate` style):
```python
def tool_call_loop(
    self,
    user_message: str,
    tools: list[dict],
    *,
    executor,  # Callable[[str, dict], dict]
    system_prompt: str = "",
    farm_context: Optional[str] = None,
    task_type: str = "ask_farm_agent",
    model: Optional[str] = None,
    max_tokens: int = 2048,
    max_iterations: int = 5,
    user_id: str = "system",
) -> "LLMResponse":
    """Standard Anthropic agent loop, bounded by max_iterations."""
    target_model = model or self._model_for_task(task_type)
    client = self._get_client()
    system_blocks = self._build_system_blocks(system_prompt, farm_context) if system_prompt else []
    messages: list[dict] = [{"role": "user", "content": user_message}]
    tools_used: list[dict] = []
    final_text = ""
    last_response = None
    t0 = time.monotonic()

    for _ in range(max_iterations):
        kwargs: dict[str, Any] = dict(
            model=target_model, max_tokens=max_tokens,
            tools=tools, messages=messages,
        )
        if system_blocks:
            kwargs["system"] = system_blocks
        last_response = client.messages.create(**kwargs)
        # Append assistant turn
        messages.append({"role": "assistant", "content": last_response.content})
        if last_response.stop_reason != "tool_use":
            final_text = " ".join(
                getattr(b, "text", "") for b in last_response.content if getattr(b, "type", "") == "text"
            ).strip()
            break
        # Execute every tool_use block, attach tool_result blocks for the next turn
        tool_results: list[dict] = []
        for block in last_response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            tools_used.append({"name": block.name, "input": block.input})
            try:
                out = executor(block.name, block.input)
            except Exception as exc:
                out = {"error": f"executor_failed: {exc}"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(out, ensure_ascii=False, default=str),
            })
        messages.append({"role": "user", "content": tool_results})
    else:
        raise RuntimeError(f"tool_call_loop exceeded max_iterations={max_iterations}")

    latency_ms = (time.monotonic() - t0) * 1000
    usage = last_response.usage
    result = LLMResponse(
        content=final_text,
        model=last_response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        latency_ms=latency_ms,
    )
    result.tools_used = tools_used
    self._log_call(
        target_model, task_type, result, user_id,
        endpoint=task_type, prompt=user_message, tools_used=tools_used,
    )
    return result
```

(`json` is already imported by client.py; verify before adding.)

- [ ] **Step 5: Add `tools_used: list[dict] = field(default_factory=list)` to `LLMResponse` dataclass** (top of `client.py` ~line 27).

- [ ] **Step 6: Run tests — must PASS**

Run: `pytest tests/web_cabinet/ai/test_tool_call_loop.py -x -q 2>&1 | tail -5`
Expected: 3 PASS.

- [ ] **Step 7: Run full ai test dir — no regressions**

Run: `pytest tests/web_cabinet/ai/ -x -q 2>&1 | tail -10`
Expected: all green.

- [ ] **Step 8: Commit Phase 3**

```bash
git add web_cabinet/ai/client.py tests/web_cabinet/ai/test_tool_call_loop.py
git commit -m "feat(P1-1): bounded agent loop AnthropicClient.tool_call_loop

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Wire agent loop into `ask_farm.py` (1 commit)

### Task 4.1: Replace pure-text live stream with agent-loop + final-text streaming

**Files:**
- Modify: `web_cabinet/ai/endpoints/ask_farm.py`
- Test: `tests/web_cabinet/ai/test_ask_farm_agent.py` (new)

- [ ] **Step 1: Write failing integration test**

Create `tests/web_cabinet/ai/test_ask_farm_agent.py`:
```python
"""Integration: ask_farm uses tool_call_loop and emits SSE tool_used events."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
# (Import test app or create minimal SSE harness via httpx + asgi.)
# Exact harness depends on existing test infra — match patterns from test_real_mode_bridge.py.
```

(See `test_real_mode_bridge.py` for SSE assertion patterns — reuse.)

The minimum-viable assertion: on a question routing to `get_animal_profile`, the SSE stream must contain at least one `tool_used` event with `name == "get_animal_profile"` before `done`.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Refactor `_stream_live` in `ask_farm.py`**

Replace the body of `_stream_live` (`web_cabinet/ai/endpoints/ask_farm.py:190–286`) with:
```python
async def _stream_live(question, session_id, user_id, farm_id, messages_history):
    from ..client import get_client
    from ..context import build_farm_context
    from ..prompts.ask_farm import ASK_FARM_SYSTEM, build_ask_farm_message
    from ..session_memory import get_session_memory
    from ..tools import ALL_TOOLS, execute_tool
    from ...storage import resolve_demo_store  # adjust import to actual store factory

    settings = get_ai_settings()
    model = settings.GENOMEAI_AI_DEFAULT_MODEL
    yield _sse_event("start", {"session_id": session_id, "model": model})

    farm_ctx = {}
    farm_ctx_text = ""
    known_event_ids = set()
    try:
        farm_ctx = build_farm_context(farm_id)
        farm_ctx_text = json.dumps(farm_ctx, ensure_ascii=False, default=str)
        known_event_ids = _extract_known_event_ids(farm_ctx)
    except Exception as exc:
        logger.warning(f"farm_context build failed farm={farm_id}: {exc}")

    user_message = build_ask_farm_message(question)
    store = resolve_demo_store(farm_id)
    client = get_client()

    # Run agent loop synchronously (uses client.messages.create, not astream)
    try:
        response = await asyncio.to_thread(
            client.tool_call_loop,
            user_message=user_message,
            tools=ALL_TOOLS,
            executor=lambda name, inp: execute_tool(name, inp, store),
            system_prompt=ASK_FARM_SYSTEM,
            farm_context=farm_ctx_text or None,
            task_type="ask_farm",
            user_id=user_id,
        )
    except Exception as exc:
        logger.error(f"ask_farm agent loop error: {exc}")
        yield _sse_event("error", {"message": "Ошибка AI-сервиса. Попробуйте позже."})
        return

    # Emit per-tool SSE events
    for tool in response.tools_used:
        yield _sse_event("tool_used", {"name": tool["name"], "input": tool.get("input", {})})

    # Stream final assistant text token-by-token (preserve frontend SSE contract)
    full_text = response.content
    for ch in full_text:
        yield _sse_event("token", {"text": ch})
        await asyncio.sleep(0)  # cooperative yield

    # Evidence parsing on the final text (existing behaviour)
    evidences = parse_evidence_from_response(full_text, known_event_ids)
    for ev in evidences:
        is_ctx_key = ev.event_id in _CONTEXT_KEY_LABELS
        name = _CONTEXT_KEY_LABELS.get(ev.event_id, ev.event_id.replace("_", " "))
        description = (
            _build_context_key_description(ev.event_id, farm_ctx)
            if is_ctx_key
            else ev.description
        )
        yield _sse_event("evidence", {
            "type": "farm_context" if is_ctx_key else "event",
            "id": ev.event_id,
            "name": name,
            "description": description,
            "verified": ev.verified,
        })

    try:
        mem = get_session_memory()
        mem.append(session_id, "user", question)
        mem.append(session_id, "assistant", full_text)
    except Exception as exc:
        logger.warning(f"session_memory.append error: {exc}")

    yield _sse_event("done", {
        "total_tokens": {"input": response.input_tokens, "output": response.output_tokens},
        "evidence_ids": [e.event_id for e in evidences],
        "validated_evidence": all(e.verified for e in evidences),
        "tools_used": [t["name"] for t in response.tools_used],
    })
```

(Adjust `resolve_demo_store` import to wherever the project actually constructs the demo store — Phase 4 research step pinpoints the symbol; if helper doesn't exist, factor it out from existing usage in tools tests.)

- [ ] **Step 4: Demo-mode preset path stays unchanged** — preset short-circuit at lines 329–347 already returns before `_stream_live`.

- [ ] **Step 5: Run integration test — PASS**

Run: `pytest tests/web_cabinet/ai/test_ask_farm_agent.py -x -q 2>&1 | tail -10`

- [ ] **Step 6: Commit Phase 4**

```bash
git add web_cabinet/ai/endpoints/ask_farm.py tests/web_cabinet/ai/test_ask_farm_agent.py
git commit -m "feat(P1-1): wire tool_call_loop into /api/ai/ask-farm SSE pipeline

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Acceptance smoke + final canonical-set test (1 commit)

### Task 5.1: 4 acceptance prompt tests through ask-farm

**Files:**
- Modify: `tests/web_cabinet/ai/test_tools_canonical_set.py`

The 4 brief-mandated prompts MUST route to the right tool. Use `monkeypatch` to replace `client.messages.create` with a recorder that asserts which tool the model would have invoked given a deterministic stub. (Mocking the model is acceptable here — we test routing wiring, not model intelligence; live-API smoke is gated by `ANTHROPIC_API_KEY` env.)

- [ ] **Step 1: Add test for 4 acceptance prompts** (per brief §P1-1 acceptance):

```python
ACCEPTANCE_PROMPTS = [
    ("покажи карточку Звёздочки", "get_animal_profile"),
    ("стоит ли выбраковать Малину", "calculate_cull_npv"),
    ("прогноз надоя на следующую неделю", "forecast_milk_yield"),
    ("как смена рациона повлияла на надой", "analyze_event_impact"),
]


@pytest.mark.parametrize("question,expected_tool", ACCEPTANCE_PROMPTS)
def test_ask_farm_routes_to_canonical_tool(question, expected_tool, ...):
    # Stub model: first response = tool_use(expected_tool); second = end_turn text.
    # Assert: tools_used in done-event includes expected_tool.
    ...
```

(Implement against the harness used in Task 4.1.)

- [ ] **Step 2: Run — PASS**

Run: `pytest tests/web_cabinet/ai/test_tools_canonical_set.py -x -q 2>&1 | tail -10`

- [ ] **Step 3: Commit**

```bash
git add tests/web_cabinet/ai/test_tools_canonical_set.py
git commit -m "test(P1-1): 4 acceptance prompts route to canonical tools

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Documentation, CI gates, execution proof (2 commits)

### Task 6.1: Update docs

**Files:**
- Modify: `docs/public_interfaces.md` (add canonical-tools section + agent loop note)
- Modify: `web_cabinet/ai/tools.py` (top-of-file docstring listing canonical 7 + extras 3)

- [ ] **Step 1: Add a "Canonical AI tools (thesis §3.1.4)" section to `docs/public_interfaces.md`** with the 7 names, descriptions, schema fingerprints, and a one-line note on `EXTRA_TOOLS`.

- [ ] **Step 2: Update tools.py module docstring**

```python
"""Canonical 7 AI tools (thesis §3.1.4) + 3 production extras.

Canonical (mentioned in dissertation):
    1. get_animal_profile        — карточка коровы
    2. analyze_event_impact      — импакт-анализ события
    3. forecast_milk_yield       — прогноз надоя
    4. calculate_cull_npv        — NPV выбраковки (P1-1: stub; P1-2: full)
    5. find_attention_cows       — TOP-N коров под наблюдением
    6. get_kpi_summary           — KPI агрегаты
    7. search_events_timeline    — поиск событий

Extras (production-only):
    8. get_treatment_records
    9. get_reproduction_status
   10. get_milk_quality_trend
"""
```

- [ ] **Step 3: Commit**

```bash
git add docs/public_interfaces.md web_cabinet/ai/tools.py
git commit -m "docs(P1-1): canonical 7 tools surface + agent loop in public_interfaces

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 6.2: Run all 7 CI gates per CLAUDE.md §4

- [ ] **Step 1: pytest gate**

```bash
bash scripts/run_ci_gate.sh 2>&1 | tee artifacts/_ci/p1-1_pytest.log | tail -20
```
Expected: zero new failures, zero new warnings.

- [ ] **Step 2: web smoke**

```bash
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json artifacts/_ci/p1-1_web_smoke.json | tee artifacts/_ci/p1-1_web_smoke.log
```

- [ ] **Step 3: golden verify_refactor**

```bash
python -m genomeai.cli verify_refactor --project-root . --golden golden \
  --report-root artifacts/_ci/p1-1_verify_refactor | tee artifacts/_ci/p1-1_verify_refactor.log
```
**MUST be zero diff** — if not, STOP and re-evaluate (no `--update-golden` without explicit ask).

- [ ] **Step 4: warning governance** — `bash scripts/run_warning_governance_gate.sh`
- [ ] **Step 5: operational rollout** — `bash scripts/run_operational_rollout_gate.sh`
- [ ] **Step 6: competitive acceptance** — `bash scripts/run_competitive_acceptance_gate.sh`
- [ ] **Step 7: performance** — `bash scripts/run_perf_gates.sh`

### Task 6.3: Write execution proof

**Files:**
- Create: `docs/iterations/T34-P1-1_execution_proof.md`

- [ ] **Step 1: Use the same template as `docs/iterations/T34-P0-1_execution_proof.md`** — Scope, Executed checks, Acceptance criteria status, Net result, Honest status (`proven` only if all 7 gates green AND 4 acceptance prompts pass).

- [ ] **Step 2: Final commit + push**

```bash
git add docs/iterations/T34-P1-1_execution_proof.md
git commit -m "docs(P1-1): execution proof for canonical tools registry + agent loop

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Acceptance criteria (final checklist)

- [ ] All 7 canonical tool names (`get_animal_profile`, `analyze_event_impact`, `forecast_milk_yield`, `calculate_cull_npv`, `find_attention_cows`, `get_kpi_summary`, `search_events_timeline`) present in `tools.py` with schemas
- [ ] Each canonical tool returns `evidence_chips`
- [ ] `tests/web_cabinet/ai/test_tools_canonical_set.py` passes locally
- [ ] 4 ask-farm acceptance prompts route to expected tools in mocked-model harness
- [ ] All 7 CI gates green (artifacts in `artifacts/_ci/p1-1_*`)
- [ ] Execution proof committed at `docs/iterations/T34-P1-1_execution_proof.md`
- [ ] Honest status: `proven`

---

## Out of scope (flagged for future tasks)

| Item | Future task |
|---|---|
| Full NPV_keep vs NPV_cull model + sensitivity | **P1-2** |
| Extending `get_animal_profile` output (last events + status block) | **P1-1b** |
| Caching agent-loop responses (Redis hit/miss) | **P1-1c** |
| Live-Anthropic acceptance smoke (gated by `ANTHROPIC_API_KEY` + billing) | manual run after Anthropic billing top-up |
