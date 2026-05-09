# Pathfinder Cleanup — Backlog for 2026-05-10

**Date queued:** 2026-05-09 (end-of-day after closing P2-1 and P3-1)
**Source audit:** `PATHFINDER-2026-05-09/02-duplication-report.md`
**Ready-to-paste prompts:** `PATHFINDER-2026-05-09/04-handoff-prompts.md`

## Context

After closing the thesis-alignment brief (P0-1, P1-1, P1-2/2b/2c, P2-1, P3-1 all `proven`), the Pathfinder audit surfaced ~1290 LOC of consolidatable duplication. Three items are queued for 2026-05-10. Priority order is **inverted** from raw LOC count because `web_cabinet/app.py` is on the legacy glide-path (CLAUDE.md §5: "новую логику не добавлять, можно только чинить existing endpoints") and polishing it has lower ROI than cleaning the AI subsystem that will move to `apps/api/`.

## Backlog (prioritized)

### 1. U6 — AI tool-executor `_filter_df` + `_format_rows` reuse  ⭐ FIRST
- **LOC:** ~30+
- **Risk:** low
- **Why first:** `web_cabinet/ai/tools.py` is the canonical 7-tool registry (P1-1 / diploma §3.1.6); will likely migrate verbatim into `apps/api/ai_tools/`. Cleaning here pays off on migration.
- **Handoff prompt:** `PATHFINDER-2026-05-09/04-handoff-prompts.md` § Handoff 4
- **Touched files:** `web_cabinet/ai/tools.py:376-678` (5 `_exec_*` functions)
- **Acceptance:** AI tool integration tests pass; tool name strings + output row schemas locked (helps grounding-rate metric); 7-gate green.

### 2. U2 — `CronJobRunner` base class for 3 AI cron files
- **LOC:** ~140
- **Risk:** low
- **Why second:** `web_cabinet/ai/background/_cron_base.py` becomes a stable extension point for the next AI cron jobs (NPV-cull alerts, recurrent-mastitis flags) — useful immediately, not speculative.
- **Handoff prompt:** `PATHFINDER-2026-05-09/04-handoff-prompts.md` § Handoff 2
- **Touched files:** `morning_brief_cron.py`, `weekly_brief_cron.py`, `insight_scanner_cron.py`
- **Acceptance:** all 3 cron jobs run on schedule (unit test + manual one-shot via `GENOMEAI_AI_CRON_TEST=true`); 7-gate green.

### 3. U1 — `@audit_action` route decorator (the elephant)  ⭐ LARGEST, LOWEST ROI HERE
- **LOC:** ~1000
- **Risk:** medium (audit-row drift if decorator drops fields silently — gate suite does NOT catch this; needs before/after audit-table diff)
- **Why third (or deferred indefinitely):** `web_cabinet/app.py` is **legacy per CLAUDE.md §5**. The 1000-LOC saving is real but the file is on the deprecation glide-path toward `apps/api/`. The right place for `@audit_action` is **fresh code in `apps/api/`**, not retrofitting legacy.
- **Recommendation:** **defer until `apps/api/` migration starts**, OR pilot on the 5 timeline routes only (smallest blast radius), then re-evaluate cost/benefit before the full fan-out.
- **Handoff prompt:** `PATHFINDER-2026-05-09/04-handoff-prompts.md` § Handoff 1
- **Touched files:** `web_cabinet/audit_decorator.py` (new) + ~92 sites in `web_cabinet/app.py`
- **Acceptance:** audit row count for any privileged action unchanged (compare via `SELECT COUNT(*) FROM audit_events WHERE action='...' GROUP BY day` before/after); 7-gate green; net delta ≥ −800 LOC after fan-out.

## Out of scope (lower-ROI Pathfinder items, queued only if time permits)

- U3 — `demo_or_live` AI gate (4 sites, ~60 LOC)
- U4 — `extract_json_from_markdown` helper (4 sites, ~12 LOC)
- U5 — `SEEDED_PATHS` registry (~15 LOC)
- U7 — `_count_event_by_type` + `_require_event_exists` micro-helpers (~12 LOC)

These can be folded opportunistically into any unrelated PR touching the affected files.

## Execution rules (per CLAUDE.md)

- One phase = one commit (no batching).
- 7-gate run before claiming `proven` on any item.
- Execution proof → `docs/iterations/T34-U6_execution_proof.md` etc., mirroring T34-P1-2c / T34-P2-1 / T34-P3-1 templates.
- If U1 (audit decorator) is attempted: **pilot on 5 timeline routes** before fan-out, with explicit before/after audit-row count parity check as part of the proof.
