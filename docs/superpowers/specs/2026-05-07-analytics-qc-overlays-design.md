# Design: Analytics — QC Overlays, Event Overlays, Fullscreen Mode

**Status:** Approved (brainstorm phase)
**Date:** 2026-05-07
**Owner:** AI assistant + project lead
**Scope:** GenomeAI AgroAnimals — `/analytics` surface (web_app + web_cabinet backend)
**Predecessor:** 2026-05-07 AI insights feature (separate spec/plan)

## 1. Problem

The Analytics tab renders charts via `web_app/components/analytics/metric-chart-card.tsx` from `lib/api/analytics.ts`. Three gaps versus product intent:

1. **No QC visualization.** Backend already detects sensor anomalies (`web_cabinet/analytics/sensor_bridge.py`) but the result is consumed only by the AI insight scanner. Operators looking at a chart cannot see *that data was unreliable in this period* — and cannot read *why*.
2. **No fullscreen view.** Charts live in a fixed grid; an operator who wants to inspect a single chart in detail has to squint.
3. **No event context.** Timeline events (rations changed, treatments, staffing) are entered manually by farm operators, but they are never overlaid onto the metrics they actually influenced.

The user wants charts that show: AI-described QC incidents as highlighted segments, manual timeline events as markers, plus a fullscreen mode — all toggleable.

## 2. Goals

1. New entity `qc_incidents` — periods of unreliable data on a specific metric, auto-detected by deterministic heuristics on real farm data, described by Claude.
2. Existing `timeline_events` get an AI-derived `linked_metric_ids[]` so events appear only on the charts they influenced.
3. Two global toggles in the analytics tab header (`show_qc`, `show_events`), persisted in `localStorage`, ON by default.
4. Hover on QC overlay or event marker shows tooltip; click opens a card / deep-links to `/timeline`.
5. Per-chart `Maximize2` icon opens a fullscreen modal of that single chart with all functions intact (rename, delete, alert, info, hover/click overlays).
6. ESC and an X-button close fullscreen.
7. Cron token-saver gate (same idea as insights cron) — no Claude calls when no new data.
8. All seven CI gates from `CLAUDE.md §4` must pass before any `proven` claim.

## 3. Non-Goals

- Manual creation of QC incidents (auto-detect only). The user explicitly preferred auto.
- Per-chart toggle UI for QC/events (toggles are global at tab level).
- Editing AI descriptions of QC incidents (dismiss is enough; if AI was wrong, dismiss).
- Backfilling QC incidents for historical milkings older than the demo window.
- Mobile-specific layout for fullscreen (the modal will work on tablet+ widths only).
- Multi-chart comparison inside fullscreen (out of scope; existing "Compare" button still works in non-fullscreen).

## 4. Architecture

```
┌─ Frontend (Next.js) ────────────────────────────────────────┐
│  /analytics page                                            │
│   ├─ AnalyticsTabs                                          │
│   │   └─ tab header: ["+ Добавить график"]  [⚙ QC]  [📍 События]│
│   ├─ Tab body (production / feed / repro / health / ...)    │
│   │   └─ MetricChartCard × N                                │
│   │       ├─ ChartCard (header w/ Maximize2)                │
│   │       └─ BiChart (canvas/SVG)                           │
│   │           ├─ <QcOverlay>     when show_qc                │
│   │           └─ <EventOverlay>  when show_events            │
│   └─ <FullscreenChartModal>  conditionally rendered          │
│       └─ wraps the same MetricChartCard                      │
│                                                             │
│   API calls:                                                │
│     /api/qc/incidents?farm_id=...&active=true               │
│     /api/qc/incidents/{id}/dismiss                          │
│     /api/timeline/events           (existing; returns       │
│                                     linked_metric_ids now)  │
└─────────────────────┬───────────────────────────────────────┘
                      │ proxy w/ auth-token forward
┌─────────────────────▼───────────────────────────────────────┐
│  Backend FastAPI (web_cabinet)                              │
│  /api/app/v1/qc/incidents/*    (boundary, new)              │
│   └─ qc_v1.py — Postgres CRUD                               │
│  Cron (every 6h):                                           │
│   └─ analytics/qc_detector.py — runs 4 deterministic checks │
│       (gap, range, stuck, flatline) + token-saver gate      │
│       Each new incident → analytics/qc_ai_describer.py      │
│        (one Claude call, cached in ai_description column)   │
│  POST /api/app/v1/timeline/events hook:                     │
│   └─ event_metric_linker.py — single Claude call            │
│       to populate linked_metric_ids                         │
└─────────────────────┬───────────────────────────────────────┘
                      │ psycopg shim
                ┌─────▼─────────────────┐
                │ qc_incidents          │  (new table)
                │ timeline_events       │  (extended col)
                │ qc_scan_state         │  (new, cron gate)
                └───────────────────────┘
```

Single source of truth: `qc_incidents` for QC, `timeline_events.linked_metric_ids` for event-metric linking. Both are server-rendered into the per-chart overlays, via one fetch per analytics tab load (not per chart).

## 5. Database Schema

Alembic migration on top of `20260507_12_insights_extend`.

### 5.1 New `qc_incidents`

```sql
CREATE TABLE IF NOT EXISTS qc_incidents (
  incident_id      TEXT PRIMARY KEY,
  farm_id          TEXT NOT NULL,
  metric_id        TEXT NOT NULL,
  period_start     TIMESTAMPTZ NOT NULL,
  period_end       TIMESTAMPTZ,                 -- NULL = ongoing
  detector_type    TEXT NOT NULL,               -- gap|range|stuck|flatline
  severity         TEXT NOT NULL DEFAULT 'warn',-- info|warn|high
  affected_sensors JSONB NOT NULL DEFAULT '[]',
  ai_description   TEXT,                        -- Claude output, cached
  root_cause       TEXT,                        -- short label (≤80 chars)
  status           TEXT NOT NULL DEFAULT 'active', -- active|resolved|dismissed
  detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS qc_incidents_farm_metric_idx
  ON qc_incidents (farm_id, metric_id, period_start)
  WHERE status = 'active';
```

### 5.2 Extend `timeline_events`

```sql
ALTER TABLE timeline_events
  ADD COLUMN IF NOT EXISTS linked_metric_ids JSONB NOT NULL DEFAULT '[]';
```

### 5.3 New `qc_scan_state` (token-saver)

```sql
CREATE TABLE IF NOT EXISTS qc_scan_state (
  farm_id            TEXT PRIMARY KEY,
  last_scan_at       TIMESTAMPTZ,
  last_skipped_reason TEXT
);
```

Mirrors `insight_scan_state` pattern from feature #1.

## 6. Backend

### 6.1 Detector (`web_cabinet/analytics/qc_detector.py` — new)

Pure-python module, no Claude calls. Operates on `dm_milkings_daily` and `dm_sensors_daily` (existing tables).

Public API:
```python
def detect_qc_incidents(farm_id: str) -> list[QcIncident]:
    """Run all heuristics and upsert resulting incidents into qc_incidents.

    Returns the list of newly created (not pre-existing) incidents.
    """
```

Four heuristics, each isolated as `_detect_<kind>(farm_id) -> list[dict]`:

- **Gap detection:** for each (animal_id, metric) in the past 14 days, find runs of >24h with no rows. Emit one incident per (metric_id, gap_start, gap_end).
- **Range violation:** flag rows where `milk_kg > 80` or `< 0`, `scc_cells_ml > 5_000_000`, etc. (thresholds in a small dict at top of module). Emit incident per contiguous run.
- **Stuck value:** for each metric, find ≥7 consecutive days where the value did not change. Emit incident.
- **Flatline:** for each day, count animals where `milk_kg == 0`. If ≥50% of the herd has zero on the same day, emit one incident covering that day.

Each heuristic returns a dict with `metric_id`, `period_start`, `period_end`, `severity`, `affected_sensors`. The orchestrator (`detect_qc_incidents`) inserts into `qc_incidents` with `ON CONFLICT DO NOTHING` keyed on `(farm_id, metric_id, period_start, detector_type)`.

### 6.2 AI describer (`web_cabinet/analytics/qc_ai_describer.py` — new)

Public API:
```python
def describe_qc_incident(incident_id: str) -> str | None:
    """Generate a short AI explanation for an incident.

    No-op if `ai_description` is already set. Single Claude call:
    short prompt with the detector output, returns ≤200 chars text +
    ≤80-char root_cause. Updates the row.

    Returns the new ai_description, or None on failure.
    """
```

Live mode (`GENOMEAI_AI_DEMO_MODE=false`) calls Claude. Demo mode loads from `data/demo/investor_v1/qc_descriptions_seeded.json` (one entry per detector_type as a placeholder).

### 6.3 Cron gate (`web_cabinet/analytics/qc_detector.py`)

```python
def cron_should_skip_qc_scan(farm_id: str) -> bool:
    """Skip when no new milkings/sensors/timeline_events since last scan."""
```

Same shape as `cron_should_skip_scan` for insights. Persisted in `qc_scan_state`. The cron entry `run_qc_scan_for_all_farms` consults the gate; manual scans (none yet) would bypass it.

### 6.4 Boundary CRUD (`web_cabinet/qc_v1.py` — new)

Postgres-backed:
```python
def list_incidents(*, farm_id: str, metric_id: str | None = None,
                   active: bool = True) -> QcIncidentsListResponse: ...
def get_incident(incident_id: str) -> QcIncident | None: ...
def dismiss_incident(incident_id: str) -> bool: ...
```

Uses the psycopg shim from `web_cabinet/insights_v1.py` (import `_conn`).

### 6.5 Boundary routes (`web_cabinet/api_boundary_v1.py`)

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/app/v1/qc/incidents` | `?farm_id=&metric_id=&active=true` filter; default `active=true`. |
| GET | `/api/app/v1/qc/incidents/{id}` | Single incident. 404 if not found. |
| POST | `/api/app/v1/qc/incidents/{id}/dismiss` | Mark `status='dismissed'`, return updated row. |

Permissions follow existing pattern (`_user_has_any(user, 'tasks.view', 'alerts.view', 'reports.view')` for reads; mutation requires `tasks.create`).

### 6.6 Event-metric linker

`web_cabinet/analytics/event_metric_linker.py` (new):
```python
def link_event_to_metrics(event: dict) -> list[str]:
    """Return list of metric_ids influenced by this event.

    Live mode: one Claude call (≤500-token prompt with event title/type/body
    plus the static metric catalog). Returns metric_id list.
    Demo mode: static category map (e.g., 'ration_change' -> feeding metrics).
    Failure: empty list, do not raise.
    """
```

Hooked into the existing `POST /api/app/v1/timeline/events` route — after insert, call `link_event_to_metrics(event)` and update `linked_metric_ids` JSONB column. Failure to link does not roll back the event.

### 6.7 Pydantic contracts (`packages/contracts/api_boundary_v1.py`)

Add:
```python
class QcIncident(BaseModel):
    incident_id: str
    farm_id: str
    metric_id: str
    period_start: str
    period_end: Optional[str] = None
    detector_type: str
    severity: str = 'warn'
    affected_sensors: list[str] = Field(default_factory=list)
    ai_description: Optional[str] = None
    root_cause: Optional[str] = None
    status: str = 'active'
    detected_at: str

class QcIncidentsListResponse(BaseModel):
    schema: str = 'genomeai.api.qc.incidents.list.v1'
    total: int = 0
    items: list[QcIncident] = Field(default_factory=list)

class QcDismissResponse(BaseModel):
    schema: str = 'genomeai.api.qc.incidents.dismiss.v1'
    incident_id: str
    status: str
```

Extend `TimelineEvent` (or whatever model is in use) with `linked_metric_ids: list[str] = Field(default_factory=list)`.

## 7. Frontend

### 7.1 New routes (`web_app/app/api/qc/`)

- `incidents/route.ts` — GET list (proxy)
- `incidents/[id]/route.ts` — GET single (proxy)
- `incidents/[id]/dismiss/route.ts` — POST (proxy)

All thin proxies, same pattern as insights routes from feature #1.

### 7.2 Typed client (`web_app/lib/api/qc-client.ts` — new)

```ts
export interface QcIncident { /* mirrors backend */ }
export async function fetchQcIncidents(params: { farmId: string; active?: boolean }): Promise<{ total: number; items: QcIncident[] }>
export async function fetchQcIncident(id: string): Promise<QcIncident>
export async function dismissQcIncident(id: string): Promise<{ incident_id: string; status: string }>
```

### 7.3 Tab header toggles

`web_app/components/analytics/analytics-tabs.tsx`: add two compact toggles before the existing `+ Добавить график` button. State persisted in `localStorage`:

- `analytics.show_qc` — default `true`
- `analytics.show_events` — default `true`

The toggles set state in a new context (`AnalyticsOverlaysContext`) consumed by all chart cards in all tabs. Default ON.

### 7.4 Chart-level overlays

`web_app/components/analytics/qc-overlay.tsx` (new) — renders translucent rectangles on top of the BiChart for each incident matching the chart's `metric_id`. Severity → color (per palette in §7 of brainstorm:
- info: `rgba(59,130,246,0.15)`
- warn: `rgba(245,158,11,0.18)`
- high: `rgba(239,68,68,0.22)`).
- Hover → tooltip with `root_cause` + first 80 chars of `ai_description` + period.
- Click → opens `<QcIncidentCard incident={...}>` (modal).

`web_app/components/analytics/event-overlay.tsx` (new) — renders vertical 1px lines + `Pin` icon on top of the BiChart for each event with `metric_id ∈ event.linked_metric_ids`.
- Hover → tooltip with `event.title` + `event_date`.
- Click → `router.push('/timeline?event=' + event_id)`.

### 7.5 Fullscreen modal

`web_app/components/analytics/fullscreen-chart-modal.tsx` (new):
- Modal at `inset:0` with backdrop, max-width `90vw`, max-height `90vh`.
- Renders the same `MetricChartCard` inside, plus a header bar with the chart title and a `Minimize2` button + ESC handler.
- All chart actions (rename, delete, alert, info) work in fullscreen.
- Overlays (QC and events) inherit the same tab-level toggles.

`MetricChartCard` gains a `Maximize2` icon in its header that opens this modal.

### 7.6 QC incident card

`web_app/components/analytics/qc-incident-card.tsx` (new):
- Modal with title, severity badge, period range, `ai_description` paragraph, list of `affected_sensors`, button "Отметить как ложное" (dismiss).
- Dismiss → calls `dismissQcIncident`, toast `Инцидент отмечен как ложный`, removes from local state.

### 7.7 Wiring

- `analytics/page.tsx` (or the tab body) fetches QC incidents and timeline events ONCE on mount/farm-change. Stored in `AnalyticsOverlaysContext`.
- Each `MetricChartCard` reads its slice (incidents/events filtered by `metric_id`) from the context.
- Toggling `show_qc` / `show_events` affects rendering only — no re-fetch needed.

### 7.8 Existing files to modify

- `web_app/components/analytics/metric-chart-card.tsx` — props for `qcIncidents`, `events`, `showQc`, `showEvents`; pass overlays to `BiChart`; add `Maximize2` icon to header.
- `web_app/components/analytics/chart-card.tsx` — adds `Maximize2` button slot.
- `web_app/components/analytics/bi-chart.tsx` — accepts `qcIncidents` and `events` arrays; renders overlay layers behind the line.
- `web_app/components/analytics/analytics-tabs.tsx` — adds the two toggles + provides `AnalyticsOverlaysContext`.
- `web_app/lib/api/timeline.ts` — extend the `TimelineEvent` type to include `linked_metric_ids: string[]`.

## 8. Error Handling and Edge Cases

| Case | Behavior |
|---|---|
| QC API returns 5xx | Toggle still shown; overlays empty; toast `QC недоступен`. Page does not break. |
| Incident with `ai_description = NULL` (Claude failed earlier) | Show `root_cause` + detector_type label only; tooltip works without AI text. |
| `period_end IS NULL` (ongoing) | Rectangle extends to the right edge of the chart; card displays `Активен` badge. |
| Multiple events on same date | Vertical lines stack with ±3px diagonal offset; hover tooltip aggregates. |
| Click QC card while in fullscreen | Card renders with `z-index: 250` over the fullscreen modal (200). |
| Metric has no QC incidents | Toggle is a no-op for that chart; no error. |
| Long `ai_description` (>200 chars) | Tooltip shows first 80 chars + `…`; full text in card. |
| Event-link Claude failure | `linked_metric_ids = []`; event still saved. No retry. |
| QC detector cron error | Logged; does not crash app startup. Token-saver gate continues. |

## 9. Tests

### 9.1 Pytest

`tests/test_qc_detector.py` (new):
- Gap detection on a 24h+ pause in `dm_milkings_daily`
- Range violation
- Stuck value (≥7 days same SCC)
- Flatline (≥50% of herd at zero on same day)
- Dismiss hides from `active=true` list
- Cron token-saver skips Claude when no new milkings/sensors

`tests/test_event_metric_linking.py` (new):
- POST event triggers an AI link call (mocked in unit test)
- Claude failure leaves `linked_metric_ids=[]` and event still saved

`tests/test_qc_v1_db.py` (new):
- list / get / dismiss roundtrip
- list filters by metric_id and active
- dismiss is idempotent

### 9.2 Playwright

Boot stack, login `admin/admin`, navigate `/analytics`. Capture in repo root:
- `analytics-qc-overlay.png` — chart with translucent QC rectangle
- `analytics-qc-tooltip.png` — hover state
- `analytics-qc-incident-card.png` — click → card open with AI text
- `analytics-qc-toggle-off.png` — toggle off, overlay gone
- `analytics-event-overlay.png` — vertical event markers
- `analytics-event-deep-link.png` — click → /timeline?event=...
- `analytics-fullscreen.png` — fullscreen modal
- `analytics-fullscreen-overlay.png` — overlays still work in fullscreen

### 9.3 Acceptance Criteria

1. `qc_incidents`, `qc_scan_state`, and the `linked_metric_ids` column exist via alembic.
2. Cron `qc_detector` finds at least 1 incident on demo data (`INV_FARM_001`).
3. Each new incident has an `ai_description` populated by Claude (live) or seed (demo).
4. Frontend `MetricChartCard` renders QC rectangles when `show_qc=true`.
5. Frontend renders event markers when `show_events=true`.
6. Tab header toggles persist in localStorage and apply to all charts.
7. Click QC rectangle → opens incident card with description + dismiss.
8. Click event marker → deep-link to `/timeline?event=<id>`.
9. `Maximize2` icon opens fullscreen modal with the same chart and all functions.
10. ESC and the X button close fullscreen.
11. Toggling overlays does not cause a re-fetch (context-only state change).
12. All 7 CI gates pass (per `CLAUDE.md §4`); pre-existing gate 5/6 regression from commit `7b08924` may persist — call out in proof.

## 10. Implementation Plan (high-level)

1. Migration `20260508_13_qc_incidents.py` (alembic).
2. Pydantic contracts: `QcIncident`, `QcIncidentsListResponse`, `QcDismissResponse`; extend `TimelineEvent` with `linked_metric_ids`.
3. `web_cabinet/qc_v1.py` (Postgres CRUD; psycopg shim).
4. `web_cabinet/analytics/qc_detector.py` (4 heuristics + cron gate + `qc_scan_state`).
5. `web_cabinet/analytics/qc_ai_describer.py` (Claude call, demo seed fallback).
6. `web_cabinet/analytics/event_metric_linker.py` (Claude call, static fallback).
7. `web_cabinet/api_boundary_v1.py` — 3 new QC routes; hook event POST.
8. Cron registration for `run_qc_scan_for_all_farms`.
9. Pytest: detector, AI describer, linker, qc_v1 CRUD.
10. Next.js API proxies (`web_app/app/api/qc/...`).
11. Typed client `web_app/lib/api/qc-client.ts`.
12. `AnalyticsOverlaysContext` + tab-level toggles.
13. `qc-overlay.tsx`, `event-overlay.tsx`, `qc-incident-card.tsx`, `fullscreen-chart-modal.tsx`.
14. Update `MetricChartCard`, `ChartCard`, `BiChart` to render overlays + Maximize2 icon.
15. Demo seed for QC incidents (so screenshots are non-empty).
16. Playwright screenshots.
17. 7 CI gates + execution proof.

Commits split per `CLAUDE.md §11`:
- migration
- backend (CRUD + detector + describer + linker + boundary + tests)
- frontend (proxies + overlays + fullscreen + integration)
- screenshots
- proof

## 11. Risks and Assumptions

- **BiChart canvas/SVG architecture** is currently line-only. Adding overlay layers (rectangles + vertical lines) requires extending the renderer. If the existing component uses a third-party chart lib, the overlay layer might already be supported via plugins; otherwise a small custom SVG layer is added in front of the chart's drawing surface. **Reading `bi-chart.tsx` is the first task in the implementation plan to confirm**.
- **Demo data may have no detectable QC incidents** in the current `dm_milkings_daily` seed. A small `scripts/seed_demo_qc.py` is added to insert one synthetic gap and one stuck-value incident so screenshots and Playwright tests are non-empty. This script refuses on `GENOMEAI_PROFILE=prod`, mirroring `seed_demo_insights.py`.
- **Claude latency for AI describer** — one call per new incident (≈2-5s). Cron is async; UI never waits. If Claude is unavailable, `ai_description` stays NULL and UI degrades gracefully to `root_cause` + detector_type.
- **Event-metric linker false positives** are acceptable — the toggle exists for a reason; the user can hide events globally if linking is noisy. We don't gate event saving on linker success.
- **Pre-existing gates 5/6 regression** from commit `7b08924` will likely still fail. Mark `partially_proven` in proof, same as feature #1.
- **localStorage availability** — assumed (modern browsers); if absent, defaults are applied and toggles function for the session only.
