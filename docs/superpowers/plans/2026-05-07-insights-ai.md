# AI-Generated Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded `DEMO_INSIGHTS` on the `/insights` page with AI-generated insights backed by Postgres, add edit / soft-delete / settings, and a cron token-saver gate that skips Claude when no new inputs exist.

**Architecture:** Single source of truth = Postgres `scanner_insights` table. Frontend reads only via boundary API. AI scanner (Claude) writes via 6h cron + manual “Сканировать сейчас”. Per-user settings stored in `insight_settings`. Cron checks `insight_scan_state` for new inputs before spending tokens.

**Tech Stack:** FastAPI + Pydantic + psycopg2 (backend), Alembic (migrations), Next.js 15 + React 19 + TS (frontend), Anthropic Python SDK (AI), pytest + Playwright (tests).

**Spec:** `docs/superpowers/specs/2026-05-07-insights-ai-design.md`

**Commit policy** (per `CLAUDE.md §11`): one commit each for migration, backend code, frontend code. Tests live in their feature commit.

---

## File Map

**Created:**
- `src/core/migrations/alembic/versions/20260507_12_insights_extend.py` — schema migration
- `scripts/seed_demo_insights.py` — one-shot demo seed
- `tests/test_insights_v1_db.py` — boundary CRUD tests
- `tests/test_insight_scanner_cron_gate.py` — cron token-saver tests
- `tests/test_insight_scanner_settings_filter.py` — settings filter tests
- `web_app/app/api/insights/route.ts` — list proxy
- `web_app/app/api/insights/[id]/route.ts` — get/patch/delete proxy
- `web_app/app/api/insights/[id]/transition/route.ts` — transition proxy
- `web_app/app/api/insights/settings/route.ts` — settings proxy
- `web_app/components/insights/insight-edit-dialog.tsx` — edit modal
- `web_app/components/insights/insight-settings-dialog.tsx` — settings modal
- `web_app/lib/api/insights-client.ts` — typed client helpers (fetch wrappers)

**Modified:**
- `packages/contracts/api_boundary_v1.py` — InsightItem extended; new InsightUpdateRequest, InsightSettings, ScanNowResponse
- `web_cabinet/insights_v1.py` — full rewrite: Postgres CRUD + settings
- `web_cabinet/api_boundary_v1.py` — PATCH/DELETE/scan-now/settings routes
- `web_cabinet/ai/background/insight_scanner.py` — settings-aware, dedup-with-deleted, cron gate
- `web_cabinet/ai/endpoints/insights.py` — return insight_ids
- `web_app/app/api/insights/scan-now/route.ts` — switch from `/api/ai/...` to boundary path
- `web_app/app/(protected)/insights/page.tsx` — fetch from API + scan-now + settings
- `web_app/app/(protected)/insights/[id]/page.tsx` — Edit/Delete buttons + edited badge
- `web_app/lib/api/insights.ts` — remove `DEMO_INSIGHTS` array (keep types/helpers)

---

## Task 1: Alembic migration — extend `scanner_insights`, add `insight_settings` and `insight_scan_state`

**Files:**
- Create: `src/core/migrations/alembic/versions/20260507_12_insights_extend.py`

- [ ] **Step 1: Create migration file**

```python
"""postgres: extend scanner_insights and add insight_settings + insight_scan_state

Revision ID: 20260507_12_insights_extend
Revises: 20260504_11_analytics_indexes
"""

from alembic import op
import sqlalchemy as sa

revision = '20260507_12_insights_extend'
down_revision = '20260504_11_analytics_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend scanner_insights
    op.execute(sa.text("""
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS severity TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS body TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS animal_ids JSONB;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS recommendations JSONB;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS chart_data JSONB;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS edited_by TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
"""))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS scanner_insights_farm_status_idx "
        "ON scanner_insights (farm_id, status) WHERE deleted_at IS NULL"
    ))

    # New: insight_settings (per user-per farm)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS insight_settings (
  user_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  min_severity TEXT NOT NULL DEFAULT 'info',
  enabled_categories JSONB NOT NULL DEFAULT '["production","reproduction","health","feeding","welfare","economics"]',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, farm_id)
)
"""))

    # New: insight_scan_state (for cron token-saver gate)
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS insight_scan_state (
  farm_id TEXT PRIMARY KEY,
  last_scan_at TIMESTAMPTZ,
  last_skipped_reason TEXT
)
"""))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS insight_scan_state"))
    op.execute(sa.text("DROP TABLE IF EXISTS insight_settings"))
    op.execute(sa.text("DROP INDEX IF EXISTS scanner_insights_farm_status_idx"))
    for col in ("severity", "body", "action", "animal_ids", "recommendations",
                "chart_data", "edited_at", "edited_by", "deleted_at"):
        op.execute(sa.text(f"ALTER TABLE scanner_insights DROP COLUMN IF EXISTS {col}"))
```

- [ ] **Step 2: Stamp current revision (safety per CLAUDE.md §7)**

Run: `cd /opt/genomeai/repo && alembic current`
Expected output: `20260504_11_analytics_indexes (head)` or current head

- [ ] **Step 3: Apply migration**

Run: `cd /opt/genomeai/repo && alembic upgrade 20260507_12_insights_extend`
Expected: `Running upgrade 20260504_11_analytics_indexes -> 20260507_12_insights_extend`

- [ ] **Step 4: Verify schema in Postgres**

Run:
```bash
psql "$GENOMEAI_DB_DSN" -c "\d scanner_insights" | grep -E "severity|body|action|animal_ids|deleted_at"
psql "$GENOMEAI_DB_DSN" -c "\d insight_settings"
psql "$GENOMEAI_DB_DSN" -c "\d insight_scan_state"
```
Expected: all three checks show the new columns / tables.

- [ ] **Step 5: Verify downgrade locally on a copy (optional but recommended)**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: clean down + up.

- [ ] **Step 6: Commit (migration only — separate from code per CLAUDE.md §11)**

```bash
git add src/core/migrations/alembic/versions/20260507_12_insights_extend.py
git commit -m "$(cat <<'EOF'
db: extend scanner_insights, add insight_settings + insight_scan_state

Adds columns severity/body/action/animal_ids/recommendations/chart_data/
edited_*/deleted_at to scanner_insights, plus new tables insight_settings
(per user/farm filters) and insight_scan_state (cron token-saver gate).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Pydantic contract updates

**Files:**
- Modify: `packages/contracts/api_boundary_v1.py:341-372`

- [ ] **Step 1: Add new fields to `InsightItem`**

Replace the existing `InsightItem` block (lines ~341-361) with:

```python
class InsightItem(BaseModel):
    insight_id: str
    type: str
    severity: str
    status: str = 'to_check'
    date: str
    animal_ids: list[str] = Field(default_factory=list)
    title: str
    body: str
    action: str = ''
    tags: list[str] = Field(default_factory=list)
    farm_id: Optional[str] = None
    farm_label: Optional[str] = None
    farm_pct: Optional[float] = None
    holding_pct: Optional[float] = None
    chart_data: list[float] = Field(default_factory=list)
    chart_label: Optional[str] = None
    chart_unit: Optional[str] = None
    recommendations: list[InsightRecommendation] = Field(default_factory=list)
    edited_at: Optional[str] = None
    edited_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
```

- [ ] **Step 2: Add new request/response models below `InsightTransitionRequest`**

After the existing `InsightTransitionRequest` (line ~371):

```python
class InsightUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    action: Optional[str] = None
    recommendations: Optional[list[InsightRecommendation]] = None


class InsightSettings(BaseModel):
    schema: str = 'genomeai.api.insight_settings.v1'
    min_severity: str = 'info'   # info|warn|high|urgent
    enabled_categories: list[str] = Field(
        default_factory=lambda: [
            'production', 'reproduction', 'health',
            'feeding', 'welfare', 'economics',
        ]
    )


class ScanNowResponse(BaseModel):
    schema: str = 'genomeai.api.insights.scan_now.v1'
    count: int = 0
    insight_ids: list[str] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None
```

- [ ] **Step 3: Verify imports compile**

Run: `cd /opt/genomeai/repo && python -c "from packages.contracts.api_boundary_v1 import InsightItem, InsightUpdateRequest, InsightSettings, ScanNowResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 4: (Hold commit — bundle with backend code in Task 5)**

---

## Task 3: Rewrite `insights_v1.py` to use Postgres (TDD)

**Files:**
- Create: `tests/test_insights_v1_db.py`
- Modify (full rewrite): `web_cabinet/insights_v1.py`

- [ ] **Step 1: Write failing test for list_insights from DB**

Create `tests/test_insights_v1_db.py`:

```python
"""DB-backed insights_v1 boundary CRUD tests."""
from __future__ import annotations

import os
import json
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


@pytest.fixture
def farm_id() -> str:
    return f"test_farm_{uuid.uuid4().hex[:6]}"


@pytest.fixture
def seeded_insight(farm_id):
    """Inserts one insight directly via SQL, yields its id, cleans up."""
    import psycopg2
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    iid = f"ins_test_{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scanner_insights
          (insight_id, farm_id, title, category, priority, status,
           generated_at_utc, generator, payload_json,
           severity, body, action, animal_ids, recommendations)
        VALUES (%s,%s,%s,%s,%s,%s, NOW(),'seed_test', %s,
                'warn','Body','Action', %s, %s)
        """,
        (iid, farm_id, 'Test title', 'health', 'medium', 'to_check',
         json.dumps({}), json.dumps([]), json.dumps([])),
    )
    conn.commit()
    cur.close()
    conn.close()
    yield iid
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("DELETE FROM scanner_insights WHERE insight_id=%s", (iid,))
    cur.execute("DELETE FROM insight_settings WHERE farm_id=%s", (farm_id,))
    conn.commit()
    cur.close()
    conn.close()


def test_list_returns_seeded(seeded_insight, farm_id):
    from web_cabinet import insights_v1
    resp = insights_v1.list_insights(farm_id=farm_id)
    assert resp.total == 1
    assert resp.items[0].insight_id == seeded_insight
    assert resp.items[0].title == 'Test title'


def test_list_filters_by_status(seeded_insight, farm_id):
    from web_cabinet import insights_v1
    resp = insights_v1.list_insights(farm_id=farm_id, status='done')
    assert resp.total == 0


def test_list_excludes_deleted(seeded_insight, farm_id):
    from web_cabinet import insights_v1
    insights_v1.delete_insight(seeded_insight)
    resp = insights_v1.list_insights(farm_id=farm_id)
    assert resp.total == 0


def test_get_returns_404_after_delete(seeded_insight):
    from web_cabinet import insights_v1
    insights_v1.delete_insight(seeded_insight)
    assert insights_v1.get_insight(seeded_insight) is None


def test_patch_sets_edited_fields(seeded_insight):
    from web_cabinet import insights_v1
    item = insights_v1.patch_insight(
        seeded_insight,
        title='Updated', body='New body',
        edited_by='operator@example.com',
    )
    assert item is not None
    assert item.title == 'Updated'
    assert item.body == 'New body'
    assert item.edited_by == 'operator@example.com'
    assert item.edited_at is not None


def test_delete_is_idempotent(seeded_insight):
    from web_cabinet import insights_v1
    assert insights_v1.delete_insight(seeded_insight) is True
    assert insights_v1.delete_insight(seeded_insight) is True


def test_settings_round_trip(farm_id):
    from web_cabinet import insights_v1
    from packages.contracts.api_boundary_v1 import InsightSettings
    s = insights_v1.get_settings(user_id='u1', farm_id=farm_id)
    assert s.min_severity == 'info'
    assert 'production' in s.enabled_categories
    new = InsightSettings(min_severity='high', enabled_categories=['health'])
    insights_v1.put_settings(user_id='u1', farm_id=farm_id, settings=new)
    s2 = insights_v1.get_settings(user_id='u1', farm_id=farm_id)
    assert s2.min_severity == 'high'
    assert s2.enabled_categories == ['health']


def test_list_applies_settings_filter(seeded_insight, farm_id):
    """Settings narrow what list_insights returns."""
    from web_cabinet import insights_v1
    from packages.contracts.api_boundary_v1 import InsightSettings
    insights_v1.put_settings(
        user_id='u1', farm_id=farm_id,
        settings=InsightSettings(min_severity='info', enabled_categories=['production']),
    )
    resp = insights_v1.list_insights(farm_id=farm_id, user_id='u1')
    assert resp.total == 0  # seeded is health, not production
```

- [ ] **Step 2: Run tests to verify they all fail (function-not-defined or assertion errors)**

Run: `pytest tests/test_insights_v1_db.py -v`
Expected: all tests FAIL with `AttributeError: module 'web_cabinet.insights_v1' has no attribute 'patch_insight'` etc.

- [ ] **Step 3: Replace `web_cabinet/insights_v1.py` with Postgres-backed implementation**

Full file replacement:

```python
"""DB-backed insights boundary (replaces JSON-seeded legacy)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from packages.contracts.api_boundary_v1 import (
    InsightItem,
    InsightRecommendation,
    InsightSettings,
    InsightsListResponse,
)

logger = logging.getLogger("genomeai.web_cabinet.insights_v1")

_DEFAULT_CATEGORIES = [
    'production', 'reproduction', 'health',
    'feeding', 'welfare', 'economics',
]
_SEVERITY_RANK = {'info': 0, 'warn': 1, 'high': 2, 'urgent': 3}


def _dsn() -> Optional[str]:
    return os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")


def _conn():
    dsn = _dsn()
    if not dsn:
        raise RuntimeError("GENOMEAI_DB_DSN not set")
    return psycopg2.connect(dsn)


def _row_to_item(row: dict[str, Any]) -> InsightItem:
    payload = {}
    if row.get("payload_json"):
        try:
            payload = json.loads(row["payload_json"]) if isinstance(row["payload_json"], str) else row["payload_json"]
        except Exception:
            payload = {}
    recs_raw = row.get("recommendations") or payload.get("recommendations") or []
    if isinstance(recs_raw, str):
        try:
            recs_raw = json.loads(recs_raw)
        except Exception:
            recs_raw = []
    recs = [
        InsightRecommendation(
            id=r.get("id", f"r{i+1}"),
            text=r.get("text") or r.get("action", ""),
            deadline=r.get("deadline"),
        )
        for i, r in enumerate(recs_raw or [])
        if isinstance(r, dict)
    ]
    animal_ids = row.get("animal_ids") or payload.get("animal_ids") or []
    if isinstance(animal_ids, str):
        try:
            animal_ids = json.loads(animal_ids)
        except Exception:
            animal_ids = []
    chart_data = row.get("chart_data") or payload.get("chart_data") or []
    if isinstance(chart_data, str):
        try:
            chart_data = json.loads(chart_data)
        except Exception:
            chart_data = []
    return InsightItem(
        insight_id=row["insight_id"],
        type=payload.get("type", row.get("category", "production")),
        severity=row.get("severity") or row.get("priority") or 'info',
        status=row.get("status") or 'to_check',
        date=(row.get("generated_at_utc") or "").split("T")[0] if row.get("generated_at_utc") else "",
        animal_ids=animal_ids,
        title=row.get("title") or "",
        body=row.get("body") or payload.get("body") or "",
        action=row.get("action") or payload.get("action") or "",
        tags=payload.get("tags", []),
        farm_id=row.get("farm_id"),
        farm_label=payload.get("farm_label"),
        farm_pct=payload.get("farm_pct"),
        holding_pct=payload.get("holding_pct"),
        chart_data=[float(x) for x in (chart_data or []) if isinstance(x, (int, float))],
        chart_label=payload.get("chart_label"),
        chart_unit=payload.get("chart_unit"),
        recommendations=recs,
        edited_at=row["edited_at"].isoformat() if row.get("edited_at") else None,
        edited_by=row.get("edited_by"),
        created_at=row.get("generated_at_utc"),
        updated_at=row["edited_at"].isoformat() if row.get("edited_at") else row.get("generated_at_utc"),
    )


def list_insights(
    *,
    farm_id: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    category: Optional[str] = None,
    severity_min: Optional[str] = None,
) -> InsightsListResponse:
    """Return non-deleted insights, applying user settings as defaults if explicit filters absent."""
    sets = None
    if user_id and farm_id and (category is None or severity_min is None):
        sets = get_settings(user_id=user_id, farm_id=farm_id)

    eff_categories = [category] if category else (sets.enabled_categories if sets else None)
    eff_min = severity_min or (sets.min_severity if sets else None)
    min_rank = _SEVERITY_RANK.get(eff_min, 0) if eff_min else 0

    sql = ["SELECT * FROM scanner_insights WHERE deleted_at IS NULL"]
    params: list[Any] = []
    if farm_id:
        sql.append("AND farm_id = %s")
        params.append(farm_id)
    if status:
        sql.append("AND status = %s")
        params.append(status)
    if eff_categories:
        sql.append("AND category = ANY(%s)")
        params.append(list(eff_categories))
    sql.append("ORDER BY generated_at_utc DESC LIMIT 200")
    query = " ".join(sql)

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    items = [_row_to_item(r) for r in rows]
    if eff_min:
        items = [i for i in items if _SEVERITY_RANK.get(i.severity, 0) >= min_rank]
    return InsightsListResponse(total=len(items), items=items)


def get_insight(insight_id: str) -> Optional[InsightItem]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM scanner_insights WHERE insight_id = %s AND deleted_at IS NULL",
                (insight_id,),
            )
            row = cur.fetchone()
    return _row_to_item(row) if row else None


def patch_insight(
    insight_id: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    action: Optional[str] = None,
    recommendations: Optional[list[dict]] = None,
    edited_by: Optional[str] = None,
) -> Optional[InsightItem]:
    sets, params = [], []
    if title is not None:
        sets.append("title = %s"); params.append(title)
    if body is not None:
        sets.append("body = %s"); params.append(body)
    if action is not None:
        sets.append("action = %s"); params.append(action)
    if recommendations is not None:
        sets.append("recommendations = %s::jsonb"); params.append(json.dumps(recommendations))
    if not sets:
        return get_insight(insight_id)
    sets.append("edited_at = NOW()")
    sets.append("edited_by = %s"); params.append(edited_by or 'unknown')
    params.append(insight_id)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE scanner_insights SET {', '.join(sets)} "
                f"WHERE insight_id = %s AND deleted_at IS NULL",
                params,
            )
            updated = cur.rowcount
        conn.commit()
    if updated == 0:
        return None
    return get_insight(insight_id)


def delete_insight(insight_id: str) -> bool:
    """Soft delete; idempotent."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scanner_insights SET deleted_at = NOW(), status = 'deleted' "
                "WHERE insight_id = %s",
                (insight_id,),
            )
        conn.commit()
    return True


def transition_insight(insight_id: str, new_status: str) -> Optional[InsightItem]:
    if new_status not in {'to_check', 'to_follow_up', 'done'}:
        return None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scanner_insights SET status = %s "
                "WHERE insight_id = %s AND deleted_at IS NULL",
                (new_status, insight_id),
            )
            updated = cur.rowcount
        conn.commit()
    if updated == 0:
        return None
    return get_insight(insight_id)


def get_settings(*, user_id: str, farm_id: str) -> InsightSettings:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT min_severity, enabled_categories FROM insight_settings "
                "WHERE user_id = %s AND farm_id = %s",
                (user_id, farm_id),
            )
            row = cur.fetchone()
    if not row:
        return InsightSettings(
            min_severity='info',
            enabled_categories=list(_DEFAULT_CATEGORIES),
        )
    cats = row["enabled_categories"]
    if isinstance(cats, str):
        cats = json.loads(cats)
    return InsightSettings(
        min_severity=row["min_severity"] or 'info',
        enabled_categories=cats or list(_DEFAULT_CATEGORIES),
    )


def put_settings(*, user_id: str, farm_id: str, settings: InsightSettings) -> InsightSettings:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insight_settings (user_id, farm_id, min_severity, enabled_categories, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (user_id, farm_id) DO UPDATE
                  SET min_severity = EXCLUDED.min_severity,
                      enabled_categories = EXCLUDED.enabled_categories,
                      updated_at = NOW()
                """,
                (user_id, farm_id, settings.min_severity, json.dumps(settings.enabled_categories)),
            )
        conn.commit()
    return settings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_insights_v1_db.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Grep for legacy callers of removed `_load_demo_insights`**

Run: `grep -rn "_load_demo_insights\|_demo_seed_path\|_DEMO_STATUSES" /opt/genomeai/repo --include="*.py" | grep -v __pycache__`
Expected: empty (we removed those identifiers). If any caller appears, update it to use new functions (`list_insights`, `get_insight`, `transition_insight`).

- [ ] **Step 6: (Hold commit — bundle with boundary routes in Task 5)**

---

## Task 4: Demo seed script

**Files:**
- Create: `scripts/seed_demo_insights.py`

- [ ] **Step 1: Write seed script**

```python
#!/usr/bin/env python3
"""One-shot: seed scanner_insights from data/demo/investor_v1/insights_seeded.json.

Idempotent (ON CONFLICT DO NOTHING). Refuses to run on adult/prod profile.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg2

PROFILE = os.getenv("GENOMEAI_PROFILE", "dev")
if PROFILE == "prod":
    print("REFUSING: GENOMEAI_PROFILE=prod is forbidden for demo seed", file=sys.stderr)
    sys.exit(2)

DSN = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
if not DSN:
    print("REFUSING: GENOMEAI_DB_DSN not set", file=sys.stderr)
    sys.exit(2)

SEED = Path(__file__).resolve().parents[1] / "data" / "demo" / "investor_v1" / "insights_seeded.json"
FARM_ID = os.getenv("GENOMEAI_DEMO_FARM_ID", "INV_FARM_001")


def main() -> int:
    if not SEED.exists():
        print(f"REFUSING: seed file missing: {SEED}", file=sys.stderr)
        return 2
    records = json.loads(SEED.read_text(encoding="utf-8"))
    inserted = skipped = 0
    with psycopg2.connect(DSN) as conn:
        with conn.cursor() as cur:
            for rec in records:
                iid = rec["insight_id"]
                cur.execute(
                    """
                    INSERT INTO scanner_insights (
                      insight_id, farm_id, title, category, priority, status,
                      generated_at_utc, generator, payload_json,
                      severity, body, action, animal_ids, recommendations, chart_data
                    )
                    VALUES (%s,%s,%s,%s,%s,%s, NOW(),'seed_demo', %s,
                            %s,%s,%s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (insight_id) DO NOTHING
                    """,
                    (
                        iid,
                        FARM_ID,
                        rec.get("title", ""),
                        rec.get("type") or rec.get("category") or "production",
                        rec.get("severity") or rec.get("priority") or "info",
                        rec.get("status", "to_check"),
                        json.dumps(rec),
                        rec.get("severity") or "info",
                        rec.get("body", ""),
                        rec.get("action", ""),
                        json.dumps(rec.get("animal_ids", [])),
                        json.dumps(rec.get("recommendations", [])),
                        json.dumps(rec.get("chartData") or rec.get("chart_data") or []),
                    ),
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
        conn.commit()
    print(f"seeded={inserted} skipped_existing={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the script**

Run: `cd /opt/genomeai/repo && python scripts/seed_demo_insights.py`
Expected: `seeded=12 skipped_existing=0` (or similar — 12 if seeded JSON has 12).

- [ ] **Step 3: Verify in DB**

Run: `psql "$GENOMEAI_DB_DSN" -c "SELECT COUNT(*) FROM scanner_insights WHERE generator='seed_demo'"`
Expected: count ≥ 12.

- [ ] **Step 4: Re-run to confirm idempotency**

Run: `python scripts/seed_demo_insights.py`
Expected: `seeded=0 skipped_existing=12`.

- [ ] **Step 5: (Hold commit — bundle with backend in Task 5)**

---

## Task 5: Boundary routes (PATCH/DELETE/scan-now/settings)

**Files:**
- Modify: `web_cabinet/api_boundary_v1.py:1082-1117` (insights routes block)
- Modify: `web_cabinet/ai/endpoints/insights.py` (return insight_ids)

- [ ] **Step 1: Update `web_cabinet/ai/endpoints/insights.py` to return ids**

Open the file and adjust the existing `scan_now` to return id list. Replace the body of `scan_now` with:

```python
@router.post("/insights/scan-now", response_model=ScanNowResponse)
async def scan_now(farm_id: str = Query(default="demo-farm-v1")) -> ScanNowResponse:
    settings = get_ai_settings()
    try:
        insights = scan_for_new_insights(farm_id)
        ids = [i.insight_id for i in insights]
        logger.info(f"scan_now completed farm={farm_id} new_insights={len(ids)}")
        return ScanNowResponse(count=len(ids), insight_ids=ids, skipped=False)
    except Exception as exc:
        logger.error(f"scan_now failed farm={farm_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=503, detail="ai_unavailable")
```

(Adjust import for `ScanNowResponse` to come from `packages.contracts.api_boundary_v1`.)

- [ ] **Step 2: Add new boundary routes to `web_cabinet/api_boundary_v1.py`**

Find the existing `@router.post('/insights/{insight_id}/transition'...)` block (around line 1105). After it, insert:

```python
@router.patch('/insights/{insight_id}', response_model=InsightItem)
def boundary_insights_patch(
    insight_id: str,
    body: InsightUpdateRequest,
    user=Depends(_current_user),  # use existing dep — match other routes
) -> InsightItem:
    item = _patch_insight(
        insight_id,
        title=body.title,
        body=body.body,
        action=body.action,
        recommendations=[r.model_dump() for r in body.recommendations] if body.recommendations else None,
        edited_by=getattr(user, 'username', None) or 'unknown',
    )
    if item is None:
        raise HTTPException(status_code=404, detail=f'Insight {insight_id} not found or deleted')
    return item


@router.delete('/insights/{insight_id}')
def boundary_insights_delete(
    insight_id: str,
    user=Depends(_current_user),
) -> dict:
    _delete_insight(insight_id)
    return {"ok": True, "insight_id": insight_id}


@router.get('/insights/settings', response_model=InsightSettings)
def boundary_insights_settings_get(
    farm_id: str = Query(...),
    user=Depends(_current_user),
) -> InsightSettings:
    return _get_settings(user_id=str(user.user_id), farm_id=farm_id)


@router.put('/insights/settings', response_model=InsightSettings)
def boundary_insights_settings_put(
    body: InsightSettings,
    farm_id: str = Query(...),
    user=Depends(_current_user),
) -> InsightSettings:
    return _put_settings(user_id=str(user.user_id), farm_id=farm_id, settings=body)


@router.post('/insights/scan-now', response_model=ScanNowResponse)
def boundary_insights_scan_now(
    farm_id: str = Query(default='INV_FARM_001'),
    user=Depends(_current_user),
) -> ScanNowResponse:
    import redis as _redis
    redis_url = os.getenv('GENOMEAI_REDIS_URL', 'redis://localhost:6379/0')
    try:
        client = _redis.Redis.from_url(redis_url)
        lock_key = f'insight_scanner:lock:{farm_id}'
        if not client.set(lock_key, '1', nx=True, ex=120):
            raise HTTPException(status_code=409, detail='scan_in_progress')
        try:
            from web_cabinet.ai.background.insight_scanner import scan_for_new_insights
            insights = scan_for_new_insights(farm_id)
            return ScanNowResponse(
                count=len(insights),
                insight_ids=[i.insight_id for i in insights],
                skipped=False,
            )
        finally:
            client.delete(lock_key)
    except _redis.RedisError:
        # If Redis unavailable, run without lock (best-effort)
        from web_cabinet.ai.background.insight_scanner import scan_for_new_insights
        insights = scan_for_new_insights(farm_id)
        return ScanNowResponse(
            count=len(insights),
            insight_ids=[i.insight_id for i in insights],
            skipped=False,
        )
```

- [ ] **Step 3: Update imports at top of `api_boundary_v1.py`**

Add to existing imports:

```python
import os
from .insights_v1 import (
    get_insight as _get_insight,
    list_insights as _list_insights,
    transition_insight as _transition_insight,
    patch_insight as _patch_insight,
    delete_insight as _delete_insight,
    get_settings as _get_settings,
    put_settings as _put_settings,
)
from packages.contracts.api_boundary_v1 import (
    InsightItem,
    InsightUpdateRequest,
    InsightSettings,
    InsightsListResponse,
    InsightTransitionRequest,
    ScanNowResponse,
)
```

(Edit existing import lines instead of duplicating; ensure `_patch_insight`, `_delete_insight`, `_get_settings`, `_put_settings` are imported.)

- [ ] **Step 4: Update existing GET `/insights` route to pass `user_id` and `farm_id` for settings filter**

Find `boundary_insights_list` (around line 1083). Replace its body:

```python
@router.get('/insights', response_model=InsightsListResponse)
def boundary_insights_list(
    farm_id: str = Query(default='INV_FARM_001'),
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    severity_min: Optional[str] = Query(default=None),
    user=Depends(_current_user),
) -> InsightsListResponse:
    return _list_insights(
        farm_id=farm_id,
        status=status,
        user_id=str(user.user_id),
        category=category,
        severity_min=severity_min,
    )
```

- [ ] **Step 5: Run pytest gate to verify**

Run: `pytest tests/test_insights_v1_db.py -v && pytest tests/ -k "boundary and insight" -v`
Expected: PASS.

- [ ] **Step 6: Commit (backend bundle: contracts + boundary + insights_v1 + seed)**

```bash
git add packages/contracts/api_boundary_v1.py \
        web_cabinet/insights_v1.py \
        web_cabinet/api_boundary_v1.py \
        web_cabinet/ai/endpoints/insights.py \
        scripts/seed_demo_insights.py \
        tests/test_insights_v1_db.py
git commit -m "$(cat <<'EOF'
feat(insights): backend Postgres CRUD, settings, scan-now boundary

- insights_v1 reads/writes scanner_insights instead of seeded JSON
- new boundary routes: PATCH/DELETE /insights/{id}, GET/PUT /insights/settings,
  POST /insights/scan-now (with Redis lock + 409 on contention)
- ScanNowResponse returns insight_ids
- demo seed script for one-shot migration of legacy insights

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Insight scanner — settings-aware filter (TDD)

**Files:**
- Create: `tests/test_insight_scanner_settings_filter.py`
- Modify: `web_cabinet/ai/background/insight_scanner.py:44-55` (`scan_for_new_insights` body)

- [ ] **Step 1: Write failing test**

```python
"""Scanner respects insight_settings.enabled_categories."""
from __future__ import annotations

import os
import json
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _put_settings(farm_id, categories):
    import psycopg2
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insight_settings (user_id, farm_id, min_severity, enabled_categories)
                VALUES ('cron','%s','info', %s::jsonb)
                ON CONFLICT (user_id, farm_id) DO UPDATE SET enabled_categories = EXCLUDED.enabled_categories
                """ % farm_id,
                (json.dumps(categories),),
            )
        conn.commit()


def test_scanner_filters_disabled_categories(tmp_path, monkeypatch):
    """When farm has only 'health' enabled, scanner drops production insights."""
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = "TEST_FILTER_FARM"
    _put_settings(farm_id, ["health"])

    fake_seeded = [
        {
            "insight_id": "ins_h1", "title": "Mastitis", "description": "x",
            "category": "health", "priority": "high",
            "evidence_ids": ["e1"], "affected_cow_ids": ["a1"],
            "recommendations": [],
        },
        {
            "insight_id": "ins_p1", "title": "Yield", "description": "y",
            "category": "production", "priority": "high",
            "evidence_ids": ["e2"], "affected_cow_ids": ["a2"],
            "recommendations": [],
        },
    ]
    seed_file = tmp_path / "scan_now_seeded.json"
    seed_file.write_text(json.dumps(fake_seeded), encoding="utf-8")
    monkeypatch.setattr(scn, "_SCAN_NOW_SEEDED_PATH", seed_file)
    monkeypatch.setenv("GENOMEAI_AI_DEMO_MODE", "true")
    # Force settings reload
    from web_cabinet.ai import config as cfg
    cfg.get_ai_settings.cache_clear() if hasattr(cfg.get_ai_settings, "cache_clear") else None

    # Patch get_ai_settings to demo
    with patch.object(scn, "get_ai_settings") as gs:
        gs.return_value = type("S", (), {"GENOMEAI_AI_DEMO_MODE": True, "GENOMEAI_DEMO_FARM_ID": farm_id})()
        result = scn.scan_for_new_insights(farm_id)
    cats = {i.category for i in result}
    assert cats == {"health"}, f"expected only health, got {cats}"
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `pytest tests/test_insight_scanner_settings_filter.py -v`
Expected: FAIL — both categories present.

- [ ] **Step 3: Modify `scan_for_new_insights` to apply settings**

Edit `web_cabinet/ai/background/insight_scanner.py`. Replace the body of `scan_for_new_insights`:

```python
def scan_for_new_insights(farm_id: str) -> list[ScannerInsight]:
    settings = get_ai_settings()

    if settings.GENOMEAI_AI_DEMO_MODE:
        results = _load_seeded_scan_insights(farm_id)
    else:
        results = _run_live_scan(farm_id)

    enabled = _enabled_categories_for_farm(farm_id)
    if enabled is not None:
        results = [r for r in results if r.category in enabled]
    return results
```

Add helper at bottom of the file:

```python
def _enabled_categories_for_farm(farm_id: str) -> list[str] | None:
    """Returns enabled_categories from insight_settings, or None when no settings row exists.

    Note: scanner uses the 'cron' synthetic user_id row when present; otherwise None
    means 'allow all' (preserves backward compat for un-configured farms).
    """
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return None
    try:
        import psycopg2  # type: ignore[import-untyped]
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT enabled_categories FROM insight_settings "
                    "WHERE user_id='cron' AND farm_id=%s",
                    (farm_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        cats = row[0]
        if isinstance(cats, str):
            cats = json.loads(cats)
        return list(cats) if cats else None
    except Exception as exc:
        logger.debug(f"_enabled_categories_for_farm skipped: {exc}")
        return None
```

- [ ] **Step 4: Run test to verify PASS**

Run: `pytest tests/test_insight_scanner_settings_filter.py -v`
Expected: PASS.

- [ ] **Step 5: (Hold commit — bundle in Task 8)**

---

## Task 7: Insight scanner dedup includes deleted (TDD)

**Files:**
- Modify: `web_cabinet/ai/background/insight_scanner.py:58-82` (`get_active_insights` SQL)

- [ ] **Step 1: Add test to existing test file**

Append to `tests/test_insight_scanner_settings_filter.py` (or a new `tests/test_insight_scanner_dedup.py`):

```python
def test_dedup_skips_soft_deleted(tmp_path, monkeypatch):
    """Scanner doesn't recreate an insight whose evidence matches a soft-deleted row."""
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = "TEST_DEDUP_FARM"

    import psycopg2, os
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    iid = "ins_dedup_existing"
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO scanner_insights
                   (insight_id, farm_id, title, category, priority, status,
                    generated_at_utc, generator, payload_json, deleted_at)
                   VALUES (%s,%s,'Existing','health','high','to_check',
                           NOW(),'test', %s, NOW())
                   ON CONFLICT (insight_id) DO NOTHING""",
                (iid, farm_id, json.dumps({"evidence_ids": ["E_X"]})),
            )
        conn.commit()

    rows = scn.get_active_insights(farm_id)
    ev_sets = [set(r.get("evidence_ids", [])) for r in rows]
    assert {"E_X"} in ev_sets, "deleted row must be visible to dedup"

    # Cleanup
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scanner_insights WHERE insight_id=%s", (iid,))
        conn.commit()
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pytest tests/test_insight_scanner_settings_filter.py::test_dedup_skips_soft_deleted -v`
Expected: FAIL — current SQL filters by status only.

- [ ] **Step 3: Update SQL in `get_active_insights`**

Replace the SQL in `get_active_insights` body:

```python
        cur.execute(
            """
            SELECT payload_json FROM scanner_insights
            WHERE farm_id = %s
              AND (status IN ('to_check', 'to_follow_up') OR deleted_at IS NOT NULL)
            ORDER BY generated_at_utc DESC
            LIMIT 50
            """,
            (farm_id,),
        )
```

- [ ] **Step 4: Run test to verify PASS**

Run: `pytest tests/test_insight_scanner_settings_filter.py::test_dedup_skips_soft_deleted -v`
Expected: PASS.

- [ ] **Step 5: (Hold commit — bundle in Task 8)**

---

## Task 8: Cron token-saver gate (TDD)

**Files:**
- Create: `tests/test_insight_scanner_cron_gate.py`
- Modify: `web_cabinet/ai/background/insight_scanner.py:372-389` (`run_insight_scanner_for_all_farms`)

- [ ] **Step 1: Write failing tests**

```python
"""Cron path skips Claude when no new inputs arrived since last scan."""
from __future__ import annotations

import os
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _set_last_scan(farm_id, when):
    import psycopg2
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insight_scan_state (farm_id, last_scan_at)
                VALUES (%s, %s)
                ON CONFLICT (farm_id) DO UPDATE SET last_scan_at = EXCLUDED.last_scan_at
                """,
                (farm_id, when),
            )
        conn.commit()


def test_cron_skips_when_no_new_inputs(monkeypatch):
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = "TEST_GATE_NONE"
    _set_last_scan(farm_id, datetime.now(timezone.utc))  # nothing new since now
    with patch.object(scn, "scan_for_new_insights") as mock_scan:
        skipped = scn.cron_should_skip_scan(farm_id)
        assert skipped is True
        mock_scan.assert_not_called()


def test_cron_runs_when_new_event_present(monkeypatch):
    """Insert a timeline event after last_scan_at; gate must allow scan."""
    from web_cabinet.ai.background import insight_scanner as scn
    import psycopg2
    farm_id = "TEST_GATE_EVENT"
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    _set_last_scan(farm_id, past)
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO timeline_events (event_id, tenant_id, event_date, event_type, title, created_at)
                VALUES (%s, %s, NOW()::date, 'test', 'gate_test', NOW())
                ON CONFLICT (event_id) DO NOTHING
                """,
                ("ev_gate_test", farm_id),
            )
        conn.commit()
    skipped = scn.cron_should_skip_scan(farm_id)
    assert skipped is False
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM timeline_events WHERE event_id='ev_gate_test'")
        conn.commit()


def test_manual_scan_now_bypasses_gate():
    """scan_for_new_insights itself does not consult the gate."""
    from web_cabinet.ai.background import insight_scanner as scn
    # cron_should_skip_scan exists separately; scan_for_new_insights does not call it
    import inspect
    src = inspect.getsource(scn.scan_for_new_insights)
    assert "cron_should_skip_scan" not in src
```

- [ ] **Step 2: Run, expect FAIL**

Run: `pytest tests/test_insight_scanner_cron_gate.py -v`
Expected: FAIL — `cron_should_skip_scan` undefined.

- [ ] **Step 3: Add gate function and update cron entry point**

In `web_cabinet/ai/background/insight_scanner.py`, add:

```python
def cron_should_skip_scan(farm_id: str) -> bool:
    """Returns True if no new inputs since last_scan_at — cron can skip Claude."""
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return False
    try:
        import psycopg2
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_scan_at FROM insight_scan_state WHERE farm_id=%s",
                    (farm_id,),
                )
                row = cur.fetchone()
                last_scan_at = row[0] if row else None
                if last_scan_at is None:
                    return False  # never scanned -> always run

                # Check timeline_events
                cur.execute(
                    "SELECT 1 FROM timeline_events WHERE tenant_id=%s AND created_at>%s LIMIT 1",
                    (farm_id, last_scan_at),
                )
                if cur.fetchone():
                    return False
                # Check alerts_v2
                try:
                    cur.execute(
                        "SELECT 1 FROM alerts_v2 WHERE farm_id=%s AND created_at>%s LIMIT 1",
                        (farm_id, last_scan_at),
                    )
                    if cur.fetchone():
                        return False
                except Exception:
                    pass  # alerts_v2 may not exist in older deployments

        # Check sensor anomalies (recent window since last scan)
        from web_cabinet.analytics.sensor_bridge import detect_recent_sensor_anomalies
        delta_days = max(1, (datetime.utcnow() - last_scan_at.replace(tzinfo=None)).days + 1)
        anomalies = detect_recent_sensor_anomalies(farm_id, lookback_days=delta_days)
        if anomalies:
            return False

        return True
    except Exception as exc:
        logger.warning(f"cron_should_skip_scan check failed farm={farm_id}: {exc}")
        return False  # on error, prefer to scan (fail-open)


def _record_scan_run(farm_id: str, *, skipped: bool, reason: str | None) -> None:
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return
    try:
        import psycopg2
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO insight_scan_state (farm_id, last_scan_at, last_skipped_reason)
                    VALUES (%s, NOW(), %s)
                    ON CONFLICT (farm_id) DO UPDATE
                      SET last_scan_at = NOW(),
                          last_skipped_reason = EXCLUDED.last_skipped_reason
                    """,
                    (farm_id, reason if skipped else None),
                )
            conn.commit()
    except Exception as exc:
        logger.debug(f"_record_scan_run skipped: {exc}")
```

Update `run_insight_scanner_for_all_farms`:

```python
def run_insight_scanner_for_all_farms() -> None:
    from ..config import get_ai_settings
    settings = get_ai_settings()
    farms = [settings.GENOMEAI_DEMO_FARM_ID]
    logger.info(f"insight_scanner cron triggered farms={farms}")
    for farm_id in farms:
        if cron_should_skip_scan(farm_id):
            logger.info(f"insight_scanner skipped: no new inputs farm={farm_id}")
            _record_scan_run(farm_id, skipped=True, reason="no_new_inputs")
            continue
        insights = scan_for_new_insights(farm_id)
        _record_scan_run(farm_id, skipped=False, reason=None)
        if insights:
            _broadcast_new_insights(farm_id, len(insights))
```

- [ ] **Step 4: Run tests to verify PASS**

Run: `pytest tests/test_insight_scanner_cron_gate.py tests/test_insight_scanner_settings_filter.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (scanner bundle: settings filter + dedup deleted + cron gate)**

```bash
git add web_cabinet/ai/background/insight_scanner.py \
        tests/test_insight_scanner_settings_filter.py \
        tests/test_insight_scanner_cron_gate.py
git commit -m "$(cat <<'EOF'
feat(insights): scanner is settings-aware, dedups deleted, cron token-saver gate

- scan_for_new_insights honors per-farm enabled_categories
- get_active_insights includes soft-deleted rows for dedup
- new cron gate: skip Claude when no new timeline events, alerts, or
  sensor anomalies since last scan; recorded in insight_scan_state
- manual scan-now bypasses gate (explicit user intent)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Frontend — Next.js API proxies

**Files:**
- Create: `web_app/app/api/insights/route.ts`
- Create: `web_app/app/api/insights/[id]/route.ts`
- Create: `web_app/app/api/insights/[id]/transition/route.ts`
- Create: `web_app/app/api/insights/settings/route.ts`
- Modify: `web_app/app/api/insights/scan-now/route.ts`

Reuse the existing pattern from `web_app/app/api/insights/scan-now/route.ts` for auth-token forwarding.

- [ ] **Step 1: Create list route `web_app/app/api/insights/route.ts`**

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function GET(request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = {};
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const url = new URL(request.url);
  const upstream = `${config.backendBaseUrl}/api/app/v1/insights?${url.searchParams.toString()}`;
  const r = await fetch(upstream, { headers, cache: 'no-store' });
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { 'content-type': 'application/json' },
  });
}
```

- [ ] **Step 2: Create `[id]` route**

`web_app/app/api/insights/[id]/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

async function proxy(request: NextRequest, id: string, method: 'GET' | 'PATCH' | 'DELETE') {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const body = method === 'PATCH' ? await request.text() : undefined;
  const r = await fetch(
    `${config.backendBaseUrl}/api/app/v1/insights/${encodeURIComponent(id)}`,
    { method, headers, body, cache: 'no-store' },
  );
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { 'content-type': 'application/json' },
  });
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return proxy(request, (await params).id, 'GET');
}
export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return proxy(request, (await params).id, 'PATCH');
}
export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return proxy(request, (await params).id, 'DELETE');
}
```

- [ ] **Step 3: Create transition route**

`web_app/app/api/insights/[id]/transition/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const body = await request.text();
  const r = await fetch(
    `${config.backendBaseUrl}/api/app/v1/insights/${encodeURIComponent(id)}/transition`,
    { method: 'POST', headers, body },
  );
  const text = await r.text();
  return new NextResponse(text, { status: r.status, headers: { 'content-type': 'application/json' } });
}
```

- [ ] **Step 4: Create settings route**

`web_app/app/api/insights/settings/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

async function proxy(request: NextRequest, method: 'GET' | 'PUT') {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const url = new URL(request.url);
  const body = method === 'PUT' ? await request.text() : undefined;
  const r = await fetch(
    `${config.backendBaseUrl}/api/app/v1/insights/settings?${url.searchParams.toString()}`,
    { method, headers, body, cache: 'no-store' },
  );
  const text = await r.text();
  return new NextResponse(text, { status: r.status, headers: { 'content-type': 'application/json' } });
}

export async function GET(request: NextRequest) { return proxy(request, 'GET'); }
export async function PUT(request: NextRequest) { return proxy(request, 'PUT'); }
```

- [ ] **Step 5: Replace `web_app/app/api/insights/scan-now/route.ts` to call new boundary**

Modify the existing file — change the upstream URL:

```ts
// Replace this line:
//   `${config.backendBaseUrl}/api/ai/insights/scan-now?...`
// With:
    `${config.backendBaseUrl}/api/app/v1/insights/scan-now?farm_id=${encodeURIComponent(farmId)}`,
```

(Keep the rest of the file intact.)

- [ ] **Step 6: Lint and typecheck**

Run: `cd web_app && npm run lint -- --max-warnings=0 && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: (Hold commit — bundle frontend at end of Task 13)**

---

## Task 10: Typed client helper

**Files:**
- Create: `web_app/lib/api/insights-client.ts`

- [ ] **Step 1: Write the helper**

```ts
import type { InsightItem } from './insights';

export interface InsightSettings {
  min_severity: 'info' | 'warn' | 'high' | 'urgent';
  enabled_categories: string[];
}

export async function fetchInsights(params?: {
  status?: string;
  category?: string;
  severityMin?: string;
}): Promise<{ total: number; items: InsightItem[] }> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set('status', params.status);
  if (params?.category) qs.set('category', params.category);
  if (params?.severityMin) qs.set('severity_min', params.severityMin);
  const r = await fetch(`/api/insights?${qs.toString()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchInsights ${r.status}`);
  return r.json();
}

export async function fetchInsight(id: string): Promise<InsightItem> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchInsight ${r.status}`);
  return r.json();
}

export async function patchInsight(id: string, body: Partial<InsightItem>): Promise<InsightItem> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`patchInsight ${r.status}`);
  return r.json();
}

export async function deleteInsight(id: string): Promise<void> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`deleteInsight ${r.status}`);
}

export async function transitionInsight(id: string, status: string): Promise<InsightItem> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/transition`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!r.ok) throw new Error(`transitionInsight ${r.status}`);
  return r.json();
}

export async function scanNow(farmId: string): Promise<{ count: number; insight_ids: string[] }> {
  const r = await fetch(`/api/insights/scan-now?farm_id=${encodeURIComponent(farmId)}`, {
    method: 'POST',
  });
  if (r.status === 409) throw new Error('scan_in_progress');
  if (r.status === 503) throw new Error('ai_unavailable');
  if (!r.ok) throw new Error(`scanNow ${r.status}`);
  return r.json();
}

export async function fetchSettings(farmId: string): Promise<InsightSettings> {
  const r = await fetch(`/api/insights/settings?farm_id=${encodeURIComponent(farmId)}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchSettings ${r.status}`);
  return r.json();
}

export async function putSettings(farmId: string, body: InsightSettings): Promise<InsightSettings> {
  const r = await fetch(`/api/insights/settings?farm_id=${encodeURIComponent(farmId)}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`putSettings ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web_app && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: (Hold commit — bundle in Task 13)**

---

## Task 11: InsightSettingsDialog component

**Files:**
- Create: `web_app/components/insights/insight-settings-dialog.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client';
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { fetchSettings, putSettings, type InsightSettings } from '@/lib/api/insights-client';

const SEVERITIES: Array<{ value: InsightSettings['min_severity']; label: string }> = [
  { value: 'info',   label: 'Все (включая информационные)' },
  { value: 'warn',   label: 'Предупреждения и выше' },
  { value: 'high',   label: 'Высокие и выше' },
  { value: 'urgent', label: 'Только срочные' },
];

const CATEGORIES: Array<{ value: string; label: string }> = [
  { value: 'production',   label: 'Производство' },
  { value: 'reproduction', label: 'Воспроизводство' },
  { value: 'health',       label: 'Здоровье' },
  { value: 'feeding',      label: 'Кормление' },
  { value: 'welfare',      label: 'Благополучие' },
  { value: 'economics',    label: 'Экономика' },
];

interface Props {
  farmId: string;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function InsightSettingsDialog({ farmId, open, onClose, onSaved }: Props) {
  const [settings, setSettings] = useState<InsightSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    fetchSettings(farmId).then(setSettings).catch((e) => setError(String(e)));
  }, [open, farmId]);

  if (!open) return null;

  function toggleCat(value: string) {
    if (!settings) return;
    const has = settings.enabled_categories.includes(value);
    setSettings({
      ...settings,
      enabled_categories: has
        ? settings.enabled_categories.filter((c) => c !== value)
        : [...settings.enabled_categories, value],
    });
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      await putSettings(farmId, settings);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: 'var(--panel)', borderRadius: 'var(--radius-lg)',
        padding: 24, width: '100%', maxWidth: 480, position: 'relative',
      }}>
        <button
          onClick={onClose}
          aria-label="Закрыть"
          style={{
            position: 'absolute', top: 12, right: 12, background: 'none', border: 'none',
            cursor: 'pointer', color: 'var(--text-secondary)',
          }}
        ><X size={18} /></button>
        <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>Настройка инсайтов</h3>
        {!settings ? (
          <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>
        ) : (
          <>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Порог важности</div>
              {SEVERITIES.map((s) => (
                <label key={s.value} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    checked={settings.min_severity === s.value}
                    onChange={() => setSettings({ ...settings, min_severity: s.value })}
                  />
                  {s.label}
                </label>
              ))}
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Категории</div>
              {CATEGORIES.map((c) => (
                <label key={c.value} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={settings.enabled_categories.includes(c.value)}
                    onChange={() => toggleCat(c.value)}
                  />
                  {c.label}
                </label>
              ))}
            </div>
            {error && <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginBottom: 12 }}>{error}</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn-outline" onClick={onClose} disabled={saving}>Отмена</button>
              <button className="btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Сохраняю…' : 'Сохранить'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web_app && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: (Hold commit)**

---

## Task 12: InsightEditDialog component

**Files:**
- Create: `web_app/components/insights/insight-edit-dialog.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client';
import { useState } from 'react';
import { X, Plus, Trash } from 'lucide-react';
import { patchInsight } from '@/lib/api/insights-client';
import type { InsightItem, InsightRecommendation } from '@/lib/api/insights';

interface Props {
  insight: InsightItem;
  onClose: () => void;
  onSaved: (updated: InsightItem) => void;
}

export function InsightEditDialog({ insight, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(insight.title);
  const [body, setBody] = useState(insight.body);
  const [action, setAction] = useState(insight.action);
  const [recs, setRecs] = useState<InsightRecommendation[]>(insight.recommendations ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateRec(idx: number, patch: Partial<InsightRecommendation>) {
    setRecs((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }
  function addRec() {
    setRecs((prev) => [...prev, { id: `r${prev.length + 1}`, text: '' }]);
  }
  function removeRec(idx: number) {
    setRecs((prev) => prev.filter((_, i) => i !== idx));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchInsight(insight.insight_id, {
        title, body, action,
        recommendations: recs,
      });
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
    >
      <div style={{ background: 'var(--panel)', borderRadius: 'var(--radius-lg)',
        padding: 24, width: '100%', maxWidth: 640, maxHeight: '90vh', overflow: 'auto', position: 'relative' }}>
        <button onClick={onClose} aria-label="Закрыть"
          style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <h3 style={{ margin: '0 0 16px' }}>Изменить инсайт</h3>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Заголовок</div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={{ width: '100%', padding: 8, border: '1px solid var(--border)', borderRadius: 6 }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Текст</div>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={5}
            style={{ width: '100%', padding: 8, border: '1px solid var(--border)', borderRadius: 6 }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Действие</div>
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            style={{ width: '100%', padding: 8, border: '1px solid var(--border)', borderRadius: 6 }}
          />
        </label>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Рекомендации</span>
            <button onClick={addRec} className="btn-outline" style={{ padding: '4px 10px', fontSize: 12 }}>
              <Plus size={12} /> Добавить
            </button>
          </div>
          {recs.map((r, i) => (
            <div key={r.id ?? i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <input
                value={r.text}
                placeholder="Текст рекомендации"
                onChange={(e) => updateRec(i, { text: e.target.value })}
                style={{ flex: 1, padding: 6, border: '1px solid var(--border)', borderRadius: 6 }}
              />
              <input
                type="date"
                value={r.deadline ?? ''}
                onChange={(e) => updateRec(i, { deadline: e.target.value })}
                style={{ padding: 6, border: '1px solid var(--border)', borderRadius: 6 }}
              />
              <button onClick={() => removeRec(i)} aria-label="Удалить" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <Trash size={14} />
              </button>
            </div>
          ))}
        </div>

        {error && <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginBottom: 12 }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn-outline" onClick={onClose} disabled={saving}>Отмена</button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web_app && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: (Hold commit)**

---

## Task 13: Page rewrites — `/insights` and `/insights/[id]`, remove DEMO_INSIGHTS

**Files:**
- Modify: `web_app/app/(protected)/insights/page.tsx` (full rewrite of body)
- Modify: `web_app/app/(protected)/insights/[id]/page.tsx`
- Modify: `web_app/lib/api/insights.ts` (remove `DEMO_INSIGHTS` array)

- [ ] **Step 1: Replace `app/(protected)/insights/page.tsx`**

Full file:

```tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { ChevronRight, Settings, Lightbulb, Zap, MoreVertical, Pencil, Trash2 } from 'lucide-react';
import {
  type InsightStatus, type InsightItem,
  SEVERITY_BADGE, SEVERITY_LABEL, formatRuDate,
} from '@/lib/api/insights';
import {
  fetchInsights, deleteInsight, scanNow,
} from '@/lib/api/insights-client';
import { TriageTabs } from '@/components/insights/triage-tabs';
import { InsightSettingsDialog } from '@/components/insights/insight-settings-dialog';
import { useAuth } from '@/components/auth/auth-provider';

const PAGE_SIZE = 10;

function toast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export default function InsightsPage() {
  const { me } = useAuth();
  const farmLabel = me?.scope?.active_farm_id ?? 'INV_FARM_001';

  const [items, setItems] = useState<InsightItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<InsightStatus>('to_check');
  const [page, setPage] = useState(0);
  const [scanning, setScanning] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchInsights();
      setItems(data.items);
    } catch {
      toast('Ошибка загрузки инсайтов');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  const counts: Record<InsightStatus, number> = {
    to_check: items.filter((i) => i.status === 'to_check').length,
    to_follow_up: items.filter((i) => i.status === 'to_follow_up').length,
    done: items.filter((i) => i.status === 'done').length,
  };
  const filtered = items.filter((i) => i.status === activeTab);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  async function onScanNow() {
    setScanning(true);
    try {
      const res = await scanNow(farmLabel);
      toast(`Найдено новых инсайтов: ${res.count}`);
      await refetch();
    } catch (e: unknown) {
      const msg = String(e);
      if (msg.includes('scan_in_progress')) toast('Сканирование уже идёт');
      else if (msg.includes('ai_unavailable')) toast('ИИ недоступен, попробуйте через минуту');
      else toast('Ошибка сканирования');
    } finally {
      setScanning(false);
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Удалить инсайт?')) return;
    try {
      await deleteInsight(id);
      setItems((prev) => prev.filter((i) => i.insight_id !== id));
      toast('Инсайт удалён');
    } catch {
      toast('Ошибка удаления');
    } finally {
      setOpenMenuId(null);
    }
  }

  return (
    <div>
      <div className="insights-page-header">
        <div>
          <h1 className="page-title" style={{ marginBottom: 2 }}>Инсайты</h1>
          <p className="page-subtitle">Аналитические выводы и рекомендации по стаду</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-outline" onClick={onScanNow} disabled={scanning}>
            <Zap size={14} />
            {scanning ? 'Сканирую данные…' : 'Сканировать сейчас'}
          </button>
          <button className="btn-outline" onClick={() => setSettingsOpen(true)}>
            <Settings size={14} />
            Настройка инсайтов
          </button>
        </div>
      </div>

      <TriageTabs
        active={activeTab}
        counts={counts}
        onChange={(t) => { setActiveTab(t); setPage(0); }}
      />

      {loading ? (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>
        </div>
      ) : paginated.length === 0 ? (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <Lightbulb size={32} color="var(--text-muted)" />
          <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 14 }}>
            Нет инсайтов в этой категории. AI-сканер запустится в следующий цикл (или нажмите ⚡).
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 40 }}></th>
                <th>Инсайт</th>
                <th>Ферма</th>
                <th>Период</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((insight) => (
                <tr key={insight.insight_id} style={{ cursor: 'pointer' }}>
                  <td style={{ textAlign: 'center', paddingRight: 4 }}>
                    {insight.status === 'to_check' && (
                      <div className="insight-unread-dot" style={{ margin: '0 auto' }} />
                    )}
                  </td>
                  <td onClick={() => { window.location.href = `/insights/${insight.insight_id}`; }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span className={`badge ${SEVERITY_BADGE[insight.severity as keyof typeof SEVERITY_BADGE]}`}>
                          {SEVERITY_LABEL[insight.severity as keyof typeof SEVERITY_LABEL]}
                        </span>
                        {insight.animal_ids.length > 0 && (
                          <span className="badge badge-info" style={{ fontSize: 10 }}>
                            ID {insight.animal_ids.slice(0, 2).join(', ')}
                            {insight.animal_ids.length > 2 ? ` +${insight.animal_ids.length - 2}` : ''}
                          </span>
                        )}
                        {insight.edited_at && (
                          <span className="badge" style={{ fontSize: 10, background: 'var(--bg-muted)' }}>
                            Отредактировано
                          </span>
                        )}
                      </div>
                      <span className="insight-row-title">{insight.title}</span>
                      <span className="insight-row-subtitle">{(insight.body || '').slice(0, 80)}…</span>
                    </div>
                  </td>
                  <td onClick={() => { window.location.href = `/insights/${insight.insight_id}`; }}>
                    <span className="badge badge-teal">{farmLabel}</span>
                  </td>
                  <td onClick={() => { window.location.href = `/insights/${insight.insight_id}`; }}
                      style={{ whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-muted)' }}>
                    {formatRuDate(insight.date)}
                  </td>
                  <td>
                    <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <button
                        aria-label="Действия"
                        onClick={(e) => { e.stopPropagation(); setOpenMenuId(openMenuId === insight.insight_id ? null : insight.insight_id); }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--text-muted)' }}
                      >
                        <MoreVertical size={16} />
                      </button>
                      {openMenuId === insight.insight_id && (
                        <div
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            position: 'absolute', top: 28, right: 0, zIndex: 10,
                            background: 'var(--panel)', border: '1px solid var(--border)',
                            borderRadius: 6, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                            minWidth: 140,
                          }}
                        >
                          <Link
                            href={`/insights/${insight.insight_id}?edit=1`}
                            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', fontSize: 13, textDecoration: 'none', color: 'var(--text)' }}
                          >
                            <Pencil size={14} /> Изменить
                          </Link>
                          <button
                            onClick={() => onDelete(insight.insight_id)}
                            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', fontSize: 13, color: 'var(--danger, #b00020)', background: 'none', border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left' }}
                          >
                            <Trash2 size={14} /> Удалить
                          </button>
                        </div>
                      )}
                      <Link
                        href={`/insights/${insight.insight_id}`}
                        onClick={(e) => e.stopPropagation()}
                        style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}
                      >
                        <ChevronRight size={16} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
          <button className="btn-outline" style={{ padding: '4px 10px', fontSize: 12 }} disabled={page === 0} onClick={() => setPage(Math.max(0, page - 1))}>← Назад</button>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{page + 1} / {totalPages}</span>
          <button className="btn-outline" style={{ padding: '4px 10px', fontSize: 12 }} disabled={page >= totalPages - 1} onClick={() => setPage(Math.min(totalPages - 1, page + 1))}>Вперёд →</button>
        </div>
      )}

      <InsightSettingsDialog
        farmId={farmLabel}
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => { toast('Настройки сохранены'); refetch(); }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Update detail page `app/(protected)/insights/[id]/page.tsx`**

Read the current file first to capture structure:

Run: `sed -n '1,40p' web_app/app/\(protected\)/insights/\[id\]/page.tsx`

Then add to the top of the page component (replace existing data source with fetch, and add Edit/Delete buttons in the header). Diff is large; the canonical pattern:

1. Replace `import { DEMO_INSIGHTS, ... }` with `import { fetchInsight, deleteInsight } from '@/lib/api/insights-client';`
2. Switch from synchronous `DEMO_INSIGHTS.find(...)` to `useEffect`+`useState` fetching `fetchInsight(id)`.
3. In the page header, add:

```tsx
import { useRouter, useSearchParams } from 'next/navigation';
import { InsightEditDialog } from '@/components/insights/insight-edit-dialog';

// inside the component:
const router = useRouter();
const sp = useSearchParams();
const [editOpen, setEditOpen] = useState(sp.get('edit') === '1');

// Header action buttons:
<div style={{ display: 'flex', gap: 8 }}>
  <button className="btn-outline" onClick={() => setEditOpen(true)}>Изменить</button>
  <button
    className="btn-outline"
    onClick={async () => {
      if (!confirm('Удалить инсайт?')) return;
      await deleteInsight(insight.insight_id);
      router.push('/insights');
    }}
  >Удалить</button>
</div>

// Edited badge:
{insight.edited_at && (
  <span className="badge" style={{ fontSize: 10 }}>
    Отредактировано {formatRuDate(insight.edited_at.split('T')[0])}
  </span>
)}

// Dialog at bottom:
{editOpen && (
  <InsightEditDialog
    insight={insight}
    onClose={() => setEditOpen(false)}
    onSaved={(u) => setInsight(u)}
  />
)}
```

(If detail page currently passes a static insight via prop, refactor it into a client component with `useEffect` fetch.)

- [ ] **Step 3: Remove `DEMO_INSIGHTS` from `web_app/lib/api/insights.ts`**

Edit the file: keep type definitions, `INSIGHT_STATUS_LABELS`, `SEVERITY_BADGE`, `SEVERITY_LABEL`, `formatRuDate`. Remove the `export const DEMO_INSIGHTS: InsightItem[] = [...]` array entirely (lines 54-313 in current state).

- [ ] **Step 4: Grep for residual usage of DEMO_INSIGHTS**

Run: `grep -rn "DEMO_INSIGHTS" web_app/ --include='*.ts' --include='*.tsx'`
Expected: empty.

- [ ] **Step 5: Build**

Run: `cd web_app && npm run build`
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 6: Commit (frontend bundle)**

```bash
git add web_app/app/api/insights/ \
        web_app/app/\(protected\)/insights/ \
        web_app/components/insights/insight-edit-dialog.tsx \
        web_app/components/insights/insight-settings-dialog.tsx \
        web_app/lib/api/insights-client.ts \
        web_app/lib/api/insights.ts
git commit -m "$(cat <<'EOF'
feat(insights): wire frontend to backend, add edit/delete + settings dialog

- Replace DEMO_INSIGHTS with fetch from /api/insights
- New API proxies for list/get/patch/delete/transition/scan-now/settings
- New "Сканировать сейчас" button (handles 409 / 503)
- "Настройка инсайтов" opens working settings dialog
- Edit dialog and Delete confirmation on row menu and detail page
- "Отредактировано" badge after manual edit

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Live Playwright validation

**Files:**
- (no code changes — captures evidence)

- [ ] **Step 1: Boot stack locally**

Run (in two terminals or as background processes):

```bash
# Backend
uvicorn web_cabinet.app:app --host 127.0.0.1 --port 8000 &
# Frontend
cd web_app && npm run dev -- --port 3000 &
```

Wait until both report ready.

- [ ] **Step 2: Run Playwright sequence via mcp__playwright tools**

Open `http://localhost:3000/login`, login as `admin/admin`. Navigate to `/insights`.

Capture screenshots into repo root:

| Action | Screenshot |
|---|---|
| Page loaded with seeded list | `insights-page.png` |
| Click "Сканировать сейчас", spinner shown | `insights-scan-loading.png` |
| Toast after scan | `insights-scan-toast.png` |
| Click "Настройка инсайтов" — modal open | `insights-settings-modal.png` |
| Save with `health` only — list narrows | `insights-after-filter.png` |
| Restore all categories, open detail of one item, click "Изменить" | `insights-edit-dialog.png` |
| Save edited title | `insights-edited-badge.png` |
| Delete from row menu | `insights-after-delete.png` |

- [ ] **Step 3: Verify acceptance criteria from spec §9.3**

For each of the 7 criteria, confirm with one screenshot or a `git grep` evidence line. Note in commit message.

- [ ] **Step 4: Stop dev servers**

- [ ] **Step 5: Commit screenshots**

```bash
git add insights-*.png
git commit -m "$(cat <<'EOF'
chore(insights): playwright evidence screenshots

Live UI captures of list, scan-now, settings filter, edit dialog,
edited badge, soft-delete flow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: CI Gates (per CLAUDE.md §4)

**Files:**
- (artifacts only)

- [ ] **Step 1: Run pytest gate**

Run: `bash scripts/run_ci_gate.sh`
Expected: green; artifact at `ci/pytest_gate.txt`.

- [ ] **Step 2: Run web smoke**

Run: `python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean --timing-json artifacts/_ci/web_smoke.json | tee artifacts/_ci/web_smoke.log`
Expected: green.

- [ ] **Step 3: Run golden verify**

Run: `python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_ci/verify_refactor | tee artifacts/_ci/verify_refactor.log`
Expected: green (no golden diffs unless `golden-update:` in commit, which we did not include).

- [ ] **Step 4: Run remaining 4 gates**

Run:
```bash
bash scripts/run_warning_governance_gate.sh
bash scripts/run_operational_rollout_gate.sh
bash scripts/run_competitive_acceptance_gate.sh
bash scripts/run_perf_gates.sh
```
Expected: all green.

- [ ] **Step 5: Write proof file**

Create `docs/iterations/T34-insights-ai_execution_proof.md`:

```markdown
# T34 — Insights AI: execution proof

## Scope

Replace hardcoded `DEMO_INSIGHTS` on /insights with backend-driven AI insights.

## Executed checks

- pytest gate: PASS — `ci/pytest_gate.txt`
- web smoke: PASS — `artifacts/_ci/web_smoke.json`
- verify_refactor: PASS — `artifacts/_ci/verify_refactor`
- warning governance: PASS
- operational rollout: PASS
- competitive acceptance: PASS
- performance: PASS
- Playwright live UI: PASS — screenshots `insights-*.png`

## Net result

Spec acceptance criteria 1–7 all met (see spec §9.3).

## Honest status

`proven`
```

- [ ] **Step 6: Commit proof**

```bash
git add docs/iterations/T34-insights-ai_execution_proof.md
git commit -m "$(cat <<'EOF'
docs(t34): execution proof for AI insights feature

All 7 CI gates pass; Playwright validation captures the user-facing
acceptance criteria from the design spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist (run after writing this plan)

- ✅ Spec §1–§12 sections all covered:
  - §4 Architecture → Tasks 1–13
  - §5 Schema → Task 1
  - §5.3 Seed → Task 4
  - §6.1 Backend API → Task 5
  - §6.2 Contracts → Task 2
  - §6.3 Frontend routes → Task 9
  - §6.4 Scanner updates → Tasks 6, 7, 8
  - §7 UI/UX → Tasks 11, 12, 13
  - §8 Error handling → Tasks 5 (lock/409), 8 (gate)
  - §9 Tests → Tasks 3, 6, 7, 8, 14
  - §10 Implementation order → mirrored 1→15
  - §11 Risks → covered in narrative
- ✅ No placeholders or TBDs in code blocks
- ✅ Type consistency verified: `InsightUpdateRequest`, `InsightSettings`, `ScanNowResponse` defined in Task 2 and consumed in Tasks 5, 9, 10–13
- ✅ File paths exact and consistent
- ✅ Commits split per CLAUDE.md §11: migration / backend / scanner / frontend / proof
