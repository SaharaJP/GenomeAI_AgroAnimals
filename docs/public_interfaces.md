# Public interfaces

Этот документ фиксирует активные публичные интерфейсы GenomeAI AgroAnimals после удаления Streamlit legacy UI (T32-12). Любые изменения CLI/API/сигнатур считаются намеренным контрактным изменением и должны сопровождаться обновлением `docs/public_interfaces.json` и контракт-тестов.

## Что зафиксировано

- CLI contract
- API routes
- Key Python functions

Streamlit contract intentionally removed after final cutover and cleanup.

## AI tool registry (canonical §3.1.4 + extras)

Source of truth: `web_cabinet/ai/tools.py` (`CANONICAL_TOOLS` and `EXTRA_TOOLS`). Public surface = the `name` field of each dict, sent verbatim to Anthropic Messages API in `tools=[...]`. Renames here are intentional contract changes.

| # | Name | Class | Required input | Notes |
|---|------|-------|----------------|-------|
| 1 | `get_animal_profile` | canonical | `cow_id` | renamed from `get_cow_history` (P1-1) |
| 2 | `analyze_event_impact` | canonical | `event_id` | added P1-1; delegates to `compute_event_impact` in `endpoints/impact_narrative.py` |
| 3 | `forecast_milk_yield` | canonical | one of `animal_id` / `group_id` | added P1-1; linear regression on DIM |
| 4 | `calculate_cull_npv` | canonical | `animal_id` | P1-2c: production-grade §3.2.4 NPV (Wood-curve, parity-stratified survival, 8-component health composite) via npv_cull.recommend() |
| 5 | `find_attention_cows` | canonical | — (`threshold_count` optional, default 10) | added P1-1 |
| 6 | `get_kpi_summary` | canonical | `group_id` | renamed from `get_group_metrics` (P1-1) |
| 7 | `search_events_timeline` | canonical | — | renamed from `search_events` (P1-1) |
| 8 | `get_treatment_records` | extra | — | unchanged |
| 9 | `get_reproduction_status` | extra | — | unchanged |
| 10 | `get_milk_quality_trend` | extra | — | unchanged |

Agent loop: `web_cabinet/ai/client.py:AnthropicClient.tool_call_loop` (sync, bounded by `max_iterations`, default 5). Wired into `POST /api/ai/ask-farm` in `web_cabinet/ai/endpoints/ask_farm.py:_stream_live` via `asyncio.to_thread`.

## Animal endpoints

| Path | Description | Source |
|---|---|---|
| `GET /api/animals/{animal_id}/cull-recommendation` | production-grade §3.2.4 NPV: per-cow Wood (1967) lactation curve, parity-stratified monthly cull-prob (Compton 2017), 8-component composite health-economic score (mastitis, late-DIM, parity, SCC, lameness, age, days-open, treatment-recurrence) folded into M_t / H_t / survival; sensitivity ≥9 cells, rationale, narrative_md; RBAC `kpi.view` | P1-2c |

## Economics endpoints

| Path | Schema | RBAC | Description | Source |
|---|---|---|---|---|
| `GET /api/app/v1/economics` | `genomeai.api.economics.list.v1` (`EconomicsListResponse`) | `whatif.scenarios.view` | what-if scenarios + reports metadata listing; back-compat surface for `/economics?tab=scenarios` UI tab | T11-01 |
| `GET /api/app/v1/economics/summary` | `genomeai.api.economics.summary.v1` (`EconomicsSummaryResponse`) | `economics.view` | computed economics overview for `/economics?tab=overview` + `?tab=strategy` UI tabs. Slice 2 fields: kpi (`total_margin_rub`, `cost_per_liter_rub`, `margin_pct`, optional `margin_per_cow_per_day_rub`), revenue (milk/cull/total), cost breakdown (feed/vet/repro/cull/other + `breakdown_pct`), `per_cow_day`, `scenarios_summary`, `formula_refs`, `warnings`. Pending slices: `sensitivity` (RFC §4.3), `unit_economics_ladder` (§4.5), `roi_actions`, `ai_cost`. Reads from `economics_v2.py` artifacts via `core.application.build_economics_summary_v1`. | T34-P2-1 RFC §3, slice 2 (2026-05-19) |
