# P0-1 AI Observability Admin Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/admin/ai` dashboard showing live LLM call telemetry (stats, grounding rate, calls table with trace drawer, manual triggers) for the GenomeAI thesis defense.

**Architecture:** New Postgres table `ai_call_log` populated best-effort by `web_cabinet/ai/client.py` on every LLM call. Four FastAPI endpoints under `/api/admin/ai/*` gated by `audit.view`. Next.js page `/admin/ai` consumes them via existing backend proxy pattern.

**Tech Stack:** Alembic + Postgres (sync), FastAPI, pytest, Next.js 15 / React 19 / TS 5.8, Playwright.

**Spec:** `docs/superpowers/specs/2026-05-09-p0-1-ai-observability-design.md` (commit `9e10ecb`).

**Commit strategy (CLAUDE.md §3):** 3 commits — migration, backend, frontend — plus a final proof commit after verification gates.

**Pragmatic deviation from spec:** Spec proposed `asyncio.create_task` for fire-and-forget DB inserts. Codebase reality: `get_db()` is **sync** (`core.infra.postgres_compat.connect_postgres_compat`) and `_log_call` is itself sync. Decision: do a sync insert with `try/except` directly in `_log_call`. AI calls are already >100 ms; +5 ms for an INSERT is invisible. Async `agenerate` path uses `asyncio.to_thread` to keep event loop free. Documented in Task 2.3.

---

## Phase 1 — Migration (commit 1)

### Task 1.1: Write the alembic migration

**Files:**
- Create: `src/core/migrations/alembic/versions/20260509_14_ai_call_log.py`

- [ ] **Step 1: Create migration file**

Path: `src/core/migrations/alembic/versions/20260509_14_ai_call_log.py`

Content:

```python
"""postgres: ai_call_log table for AI observability admin panel

Revision ID: 20260509_14_ai_call_log
Revises: 20260507_13_qc_incidents
"""
from alembic import op
import sqlalchemy as sa

revision = '20260509_14_ai_call_log'
down_revision = '20260507_13_qc_incidents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS ai_call_log (
  id                    BIGSERIAL PRIMARY KEY,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  user_id               VARCHAR(64),
  endpoint              VARCHAR(64) NOT NULL,
  task_type             VARCHAR(32) NOT NULL,
  model                 VARCHAR(64) NOT NULL,
  input_tokens          INTEGER NOT NULL DEFAULT 0,
  output_tokens         INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
  cost_usd              NUMERIC(10, 6) NOT NULL DEFAULT 0,
  latency_ms            INTEGER NOT NULL DEFAULT 0,
  error                 TEXT,
  prompt                TEXT,
  response              TEXT,
  evidence_chips        JSONB,
  tools_used            JSONB
)
"""))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_ai_call_log_created_at "
        "ON ai_call_log (created_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_ai_call_log_endpoint "
        "ON ai_call_log (endpoint)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_ai_call_log_user_id "
        "ON ai_call_log (user_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_call_log_user_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_call_log_endpoint"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_call_log_created_at"))
    op.execute(sa.text("DROP TABLE IF EXISTS ai_call_log"))
```

- [ ] **Step 2: Apply upgrade**

Run:
```bash
alembic -c alembic.ini upgrade head
```
Expected: `Running upgrade 20260507_13_qc_incidents -> 20260509_14_ai_call_log` printed; no errors.

- [ ] **Step 3: Verify table exists**

Run:
```bash
psql "$GENOMEAI_DB_DSN" -c "\d ai_call_log" 2>&1 | head -30
```
Expected: 17 columns + 3 indexes (`ix_ai_call_log_*`).

- [ ] **Step 4: Verify downgrade**

Run:
```bash
alembic -c alembic.ini downgrade -1
psql "$GENOMEAI_DB_DSN" -c "\d ai_call_log" 2>&1 | head -3
```
Expected: `Did not find any relation named "ai_call_log"`.

- [ ] **Step 5: Re-apply (idempotency)**

Run:
```bash
alembic -c alembic.ini upgrade head
psql "$GENOMEAI_DB_DSN" -c "SELECT COUNT(*) FROM ai_call_log"
```
Expected: `0` (table exists, empty).

- [ ] **Step 6: Commit migration**

```bash
git add src/core/migrations/alembic/versions/20260509_14_ai_call_log.py
git commit -m "$(cat <<'EOF'
feat(P0-1): db migration ai_call_log for AI observability

Add ai_call_log table with 17 columns (token economics, latency,
prompt/response trace, evidence_chips, tools_used JSONB) and 3 indexes
(created_at DESC, endpoint, user_id) supporting /admin/ai dashboard.
Verified upgrade/downgrade cycle on adult/test profile.

Spec: docs/superpowers/specs/2026-05-09-p0-1-ai-observability-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Backend (commit 2)

### Task 2.1: Pricing module — failing test first

**Files:**
- Create: `tests/web_cabinet/ai/test_pricing.py`
- Create: `web_cabinet/ai/pricing.py`

- [ ] **Step 1: Write the failing test**

Path: `tests/web_cabinet/ai/test_pricing.py`

```python
"""Tests for AI pricing module."""
from web_cabinet.ai.pricing import compute_cost_usd


def test_sonnet_pricing_basic():
    # 1M input + 100K output for sonnet-4-6: 3.00 + 0.1*15.00 = 4.50
    cost = compute_cost_usd("claude-sonnet-4-6", 1_000_000, 100_000, 0, 0)
    assert abs(cost - 4.50) < 1e-6


def test_opus_pricing_basic():
    # 1M input + 100K output for opus-4-7: 15.00 + 0.1*75.00 = 22.50
    cost = compute_cost_usd("claude-opus-4-7", 1_000_000, 100_000, 0, 0)
    assert abs(cost - 22.50) < 1e-6


def test_haiku_pricing_basic():
    # 1M input + 100K output for haiku-4-5: 1.00 + 0.1*5.00 = 1.50
    cost = compute_cost_usd("claude-haiku-4-5", 1_000_000, 100_000, 0, 0)
    assert abs(cost - 1.50) < 1e-6


def test_cache_tokens_charged_separately():
    # 100K cache_create + 1M cache_read for sonnet
    # cache_create: 0.1 * 3.75 = 0.375
    # cache_read: 1.0 * 0.30 = 0.30
    cost = compute_cost_usd("claude-sonnet-4-6", 0, 0, 100_000, 1_000_000)
    assert abs(cost - 0.675) < 1e-6


def test_unknown_model_returns_zero():
    cost = compute_cost_usd("gpt-5-imaginary", 1_000_000, 100_000, 0, 0)
    assert cost == 0.0


def test_empty_call_returns_zero():
    cost = compute_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0)
    assert cost == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web_cabinet/ai/test_pricing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'web_cabinet.ai.pricing'`.

- [ ] **Step 3: Implement pricing module**

Path: `web_cabinet/ai/pricing.py`

```python
"""Anthropic pricing per million tokens, USD; verified 2026-05.
Revisit quarterly via https://www.anthropic.com/pricing
"""
from __future__ import annotations

PRICES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_create": 3.75},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.00, "cache_read": 1.50, "cache_create": 18.75},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00,  "cache_read": 0.10, "cache_create": 1.25},
}


def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Return call cost in USD. Unknown model -> 0.0 (do not raise)."""
    rates = PRICES_USD_PER_MTOK.get(model)
    if rates is None:
        return 0.0
    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_creation_tokens * rates["cache_create"]
        + cache_read_tokens * rates["cache_read"]
    ) / 1_000_000
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web_cabinet/ai/test_pricing.py -v`
Expected: 6 passed.

---

### Task 2.2: ai_call_log persistence helper — failing test first

**Files:**
- Create: `tests/web_cabinet/ai/test_call_log_persistence.py`
- Create: `web_cabinet/ai/call_log.py`

- [ ] **Step 1: Write the failing test**

Path: `tests/web_cabinet/ai/test_call_log_persistence.py`

```python
"""Tests for ai_call_log persistence helper (best-effort)."""
from unittest.mock import MagicMock

import pytest

from web_cabinet.ai.call_log import persist_ai_call, _truncate


def test_truncate_preserves_short_text():
    assert _truncate("hello") == "hello"


def test_truncate_caps_at_50kb_with_marker():
    long = "x" * 60_000
    out = _truncate(long)
    assert out.startswith("[TRUNCATED:")
    assert len(out) < 51_500  # marker + 50KB body


def test_persist_inserts_row():
    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

    persist_ai_call(
        conn=fake_conn,
        endpoint="morning-brief",
        task_type="default",
        model="claude-sonnet-4-6",
        user_id="admin",
        input_tokens=100,
        output_tokens=50,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        latency_ms=850,
        error=None,
        prompt="привет",
        response="ответ",
        evidence_chips=["chip1"],
        tools_used=[{"name": "get_kpi_summary"}],
    )
    fake_cursor.execute.assert_called_once()
    fake_conn.commit.assert_called_once()


def test_persist_swallows_exceptions(caplog):
    fake_conn = MagicMock()
    fake_conn.cursor.side_effect = RuntimeError("db down")

    persist_ai_call(
        conn=fake_conn,
        endpoint="ask-farm",
        task_type="default",
        model="claude-sonnet-4-6",
        user_id=None,
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        latency_ms=0,
        error="kaboom",
        prompt=None,
        response=None,
        evidence_chips=None,
        tools_used=None,
    )
    # No exception raised. Warning logged.
    assert any("ai_call_log persist failed" in rec.message for rec in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web_cabinet/ai/test_call_log_persistence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'web_cabinet.ai.call_log'`.

- [ ] **Step 3: Implement call_log module**

Path: `web_cabinet/ai/call_log.py`

```python
"""Best-effort persistence of LLM call records into ai_call_log."""
from __future__ import annotations

import json
import logging
from typing import Any

from .pricing import compute_cost_usd

logger = logging.getLogger("genomeai.ai.call_log")

_MAX_TEXT_BYTES = 50_000


def _truncate(text: str | None) -> str | None:
    if text is None:
        return None
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_TEXT_BYTES:
        return text
    kb = len(encoded) // 1024
    body = encoded[:_MAX_TEXT_BYTES].decode("utf-8", errors="replace")
    return f"[TRUNCATED:{kb}kb]\n{body}"


def persist_ai_call(
    *,
    conn: Any,
    endpoint: str,
    task_type: str,
    model: str,
    user_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    latency_ms: float,
    error: str | None,
    prompt: str | None,
    response: str | None,
    evidence_chips: list[str] | None,
    tools_used: list[dict] | None,
) -> None:
    """Insert one row into ai_call_log. Never raises."""
    try:
        cost = compute_cost_usd(
            model, input_tokens, output_tokens,
            cache_creation_tokens, cache_read_tokens,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_call_log (
                    user_id, endpoint, task_type, model,
                    input_tokens, output_tokens,
                    cache_creation_tokens, cache_read_tokens,
                    cost_usd, latency_ms, error,
                    prompt, response, evidence_chips, tools_used
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb
                )
                """,
                (
                    user_id, endpoint, task_type, model,
                    int(input_tokens), int(output_tokens),
                    int(cache_creation_tokens), int(cache_read_tokens),
                    float(cost), int(latency_ms), error,
                    _truncate(prompt), _truncate(response),
                    json.dumps(evidence_chips or [], ensure_ascii=False),
                    json.dumps(tools_used or [], ensure_ascii=False),
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("ai_call_log persist failed: %s", exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web_cabinet/ai/test_call_log_persistence.py -v`
Expected: 4 passed.

---

### Task 2.3: Hook persistence into AnthropicClient._log_call

**Files:**
- Modify: `web_cabinet/ai/client.py:104-126`

- [ ] **Step 1: Read current `_log_call` signature**

Run: `sed -n '100,135p' web_cabinet/ai/client.py`

Expected output (current):
```python
def _log_call(
    self,
    model: str,
    task_type: str,
    response: Optional[LLMResponse],
    user_id: Optional[str],
    error: Optional[str] = None,
) -> None:
    record = {
        "event": "llm_call",
        "model": model,
        ...
    }
    logger.info(json.dumps(record, ensure_ascii=False))
```

- [ ] **Step 2: Extend `_log_call` with persistence call**

Edit `web_cabinet/ai/client.py`. Replace the existing `_log_call` body (lines ~104–126) with:

```python
def _log_call(
    self,
    model: str,
    task_type: str,
    response: Optional[LLMResponse],
    user_id: Optional[str],
    error: Optional[str] = None,
    *,
    endpoint: str = "unknown",
    prompt: Optional[str] = None,
    evidence_chips: Optional[list] = None,
    tools_used: Optional[list] = None,
) -> None:
    record = {
        "event": "llm_call",
        "model": model,
        "task_type": task_type,
        "user_id": user_id,
        "endpoint": endpoint,
        "input_tokens": response.input_tokens if response else 0,
        "output_tokens": response.output_tokens if response else 0,
        "cache_hit": response.cache_hit if response else False,
        "cache_creation_tokens": response.cache_creation_tokens if response else 0,
        "cache_read_tokens": response.cache_read_tokens if response else 0,
        "latency_ms": response.latency_ms if response else 0,
        "error": error,
    }
    logger.info(json.dumps(record, ensure_ascii=False))

    # Best-effort persistence to ai_call_log (sync, swallows all errors).
    try:
        from core.infra.postgres_compat import connect_postgres_compat
        from .call_log import persist_ai_call

        conn = connect_postgres_compat()
        try:
            persist_ai_call(
                conn=conn,
                endpoint=endpoint,
                task_type=task_type,
                model=model,
                user_id=user_id,
                input_tokens=response.input_tokens if response else 0,
                output_tokens=response.output_tokens if response else 0,
                cache_creation_tokens=response.cache_creation_tokens if response else 0,
                cache_read_tokens=response.cache_read_tokens if response else 0,
                latency_ms=int(response.latency_ms) if response else 0,
                error=error,
                prompt=prompt,
                response=response.content if response else None,
                evidence_chips=evidence_chips,
                tools_used=tools_used,
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_call_log connect failed: %s", exc)
```

- [ ] **Step 3: Update sync `generate()` _log_call call sites to pass endpoint and prompt**

Edit `web_cabinet/ai/client.py:130-200` (the `generate` method).

Find:
```python
self._log_call(target_model, task_type, result, user_id)
```
(around line 174)

Replace with:
```python
self._log_call(
    target_model, task_type, result, user_id,
    endpoint=task_type, prompt=user_message,
)
```

Find (error path, around line 195):
```python
self._log_call(target_model, task_type, dummy, user_id, error=str(last_error))
```

Replace with:
```python
self._log_call(
    target_model, task_type, dummy, user_id,
    error=str(last_error), endpoint=task_type, prompt=user_message,
)
```

- [ ] **Step 4: Update async `agenerate()` _log_call call sites identically**

Repeat the same two replacements inside `agenerate()` (around lines 242 and 263).

- [ ] **Step 5: Run AI client tests to verify nothing broke**

Run: `pytest tests/web_cabinet/ai/test_client.py -v`
Expected: existing tests pass (none reference `_log_call` directly).

- [ ] **Step 6: Run full pricing + call_log tests**

Run: `pytest tests/web_cabinet/ai/test_pricing.py tests/web_cabinet/ai/test_call_log_persistence.py -v`
Expected: 10 passed.

---

### Task 2.4: Backend stats endpoint — failing test first

**Files:**
- Create: `tests/web_cabinet/admin/__init__.py` (empty)
- Create: `tests/web_cabinet/admin/test_ai_observability.py`
- Create: `web_cabinet/admin/__init__.py` (empty)
- Create: `web_cabinet/admin/ai_observability.py`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p web_cabinet/admin tests/web_cabinet/admin
touch web_cabinet/admin/__init__.py tests/web_cabinet/admin/__init__.py
```

- [ ] **Step 2: Write the failing test**

Path: `tests/web_cabinet/admin/test_ai_observability.py`

```python
"""Tests for /api/admin/ai/* endpoints."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app_client():
    os.environ.setdefault("GENOMEAI_DB_DSN", os.environ.get("TEST_PG_DSN", "postgresql://localhost/genomeai_test"))
    from web_cabinet.app import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(app_client) -> str:
    resp = app_client.post(
        "/api/app/v1/auth/login",
        json={"username": "admin", "password": "admin", "tenant_id": "default"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["tokens"]["access_token"]


def _seed_call(conn, **kwargs):
    defaults = dict(
        user_id="admin", endpoint="ask-farm", task_type="default",
        model="claude-sonnet-4-6",
        input_tokens=100, output_tokens=50,
        cache_creation_tokens=0, cache_read_tokens=0,
        cost_usd=0.001, latency_ms=850, error=None,
        prompt="тест", response="ответ",
        evidence_chips='[]', tools_used='[]',
    )
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(["%s"] * len(defaults))
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO ai_call_log ({cols}) VALUES ({placeholders}) RETURNING id",
            tuple(defaults.values()),
        )
        row = cur.fetchone()
    conn.commit()
    return row[0]


def test_stats_requires_auth(app_client):
    resp = app_client.get("/api/admin/ai/stats")
    assert resp.status_code in (401, 403)


def test_stats_happy_path(app_client, admin_token):
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ai_call_log WHERE endpoint LIKE 'test_stats_%'")
    conn.commit()
    for i in range(5):
        _seed_call(conn, endpoint="test_stats_a", latency_ms=100 + i*100, cost_usd=0.01)
    conn.close()

    resp = app_client.get(
        "/api/admin/ai/stats?period_hours=24",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] >= 5
    assert "p50_latency_ms" in data
    assert "p95_latency_ms" in data
    assert data["total_cost_usd"] >= 0.05
    assert data["error_count"] >= 0


def test_calls_list(app_client, admin_token):
    resp = app_client.get(
        "/api/admin/ai/calls?limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:
        row = body[0]
        # Trace fields not in list view
        assert "prompt" not in row
        assert "response" not in row
        # Summary fields present
        for key in ("id", "created_at", "endpoint", "model", "latency_ms", "total_tokens", "cost_usd", "has_error"):
            assert key in row, f"missing {key}"


def test_call_detail(app_client, admin_token):
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    call_id = _seed_call(conn, endpoint="test_detail", prompt="тест-prompt", response="тест-resp")
    conn.close()

    resp = app_client.get(
        f"/api/admin/ai/calls/{call_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == call_id
    assert data["prompt"] == "тест-prompt"
    assert data["response"] == "тест-resp"


def test_call_detail_404(app_client, admin_token):
    resp = app_client.get(
        "/api/admin/ai/calls/99999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_grounding_rate(app_client, admin_token):
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ai_call_log WHERE endpoint LIKE 'test_grounding_%'")
    conn.commit()
    _seed_call(conn, endpoint="test_grounding_with", evidence_chips='["chip1"]')
    _seed_call(conn, endpoint="test_grounding_with", evidence_chips='["chip1","chip2"]')
    _seed_call(conn, endpoint="test_grounding_without", evidence_chips='[]')
    conn.close()

    resp = app_client.get(
        "/api/admin/ai/grounding-rate?period_hours=1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    assert body["with_evidence"] >= 2
    assert body["without_evidence"] >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/web_cabinet/admin/test_ai_observability.py -v`
Expected: FAIL — endpoints return 404 because router is not registered.

- [ ] **Step 4: Implement the observability router**

Path: `web_cabinet/admin/ai_observability.py`

```python
"""Admin AI observability — /api/admin/ai/* endpoints."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_db
from ..rbac import require_permissions

logger = logging.getLogger("genomeai.admin.ai_observability")

router = APIRouter(prefix="/api/admin/ai", tags=["admin-ai-observability"])

_ALLOWED_PERIODS = (1, 24, 168)


def _validate_period(period_hours: int) -> int:
    if period_hours not in _ALLOWED_PERIODS:
        raise HTTPException(status_code=400, detail={"error": "invalid_period", "allowed": list(_ALLOWED_PERIODS)})
    return period_hours


@router.get("/stats")
def stats(
    period_hours: int = Query(24, ge=1, le=168),
    user=Depends(require_permissions("audit.view")),
    conn=Depends(get_db),
) -> dict[str, Any]:
    _validate_period(period_hours)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) AS count,
              COALESCE(percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms), 0) AS p50,
              COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95,
              COALESCE(SUM(input_tokens), 0) AS total_input,
              COALESCE(SUM(output_tokens), 0) AS total_output,
              COALESCE(SUM(cost_usd), 0) AS total_cost,
              COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors
            FROM ai_call_log
            WHERE created_at >= NOW() - make_interval(hours => %s)
            """,
            (period_hours,),
        )
        row = cur.fetchone()
    count = int(row[0] or 0)
    errors = int(row[6] or 0)
    return {
        "period_hours": period_hours,
        "count": count,
        "p50_latency_ms": int(row[1] or 0),
        "p95_latency_ms": int(row[2] or 0),
        "total_input_tokens": int(row[3] or 0),
        "total_output_tokens": int(row[4] or 0),
        "total_tokens": int(row[3] or 0) + int(row[4] or 0),
        "total_cost_usd": float(row[5] or 0),
        "error_count": errors,
        "error_rate": (errors / count) if count > 0 else 0.0,
    }


@router.get("/calls")
def calls(
    limit: int = Query(100, ge=1, le=500),
    endpoint: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, regex="^(ok|error)$"),
    user=Depends(require_permissions("audit.view")),
    conn=Depends(get_db),
) -> list[dict[str, Any]]:
    where = ["1=1"]
    params: list[Any] = []
    if endpoint:
        where.append("endpoint = %s")
        params.append(endpoint)
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)
    if status == "ok":
        where.append("error IS NULL")
    elif status == "error":
        where.append("error IS NOT NULL")
    sql = f"""
        SELECT id, created_at, endpoint, model, user_id, latency_ms,
               (input_tokens + output_tokens) AS total_tokens,
               cost_usd, (error IS NOT NULL) AS has_error
        FROM ai_call_log
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT %s
    """
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "created_at": r[1].isoformat() if r[1] else None,
            "endpoint": r[2],
            "model": r[3],
            "user_id": r[4],
            "latency_ms": int(r[5] or 0),
            "total_tokens": int(r[6] or 0),
            "cost_usd": float(r[7] or 0),
            "has_error": bool(r[8]),
        }
        for r in rows
    ]


@router.get("/calls/{call_id}")
def call_detail(
    call_id: int,
    user=Depends(require_permissions("audit.view")),
    conn=Depends(get_db),
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, created_at, user_id, endpoint, task_type, model,
                   input_tokens, output_tokens,
                   cache_creation_tokens, cache_read_tokens,
                   cost_usd, latency_ms, error,
                   prompt, response, evidence_chips, tools_used
            FROM ai_call_log
            WHERE id = %s
            """,
            (call_id,),
        )
        r = cur.fetchone()
    if r is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "call_id": call_id})

    def _parse_json(value):
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return None

    return {
        "id": r[0],
        "created_at": r[1].isoformat() if r[1] else None,
        "user_id": r[2],
        "endpoint": r[3],
        "task_type": r[4],
        "model": r[5],
        "input_tokens": int(r[6] or 0),
        "output_tokens": int(r[7] or 0),
        "cache_creation_tokens": int(r[8] or 0),
        "cache_read_tokens": int(r[9] or 0),
        "cost_usd": float(r[10] or 0),
        "latency_ms": int(r[11] or 0),
        "error": r[12],
        "prompt": r[13],
        "response": r[14],
        "evidence_chips": _parse_json(r[15]),
        "tools_used": _parse_json(r[16]),
    }


@router.get("/grounding-rate")
def grounding_rate(
    period_hours: int = Query(24, ge=1, le=168),
    user=Depends(require_permissions("audit.view")),
    conn=Depends(get_db),
) -> dict[str, Any]:
    _validate_period(period_hours)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(evidence_chips, '[]'::jsonb)) > 0) AS with_evidence,
              COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(evidence_chips, '[]'::jsonb)) = 0) AS without_evidence,
              COUNT(*) AS total
            FROM ai_call_log
            WHERE created_at >= NOW() - make_interval(hours => %s)
            """,
            (period_hours,),
        )
        r = cur.fetchone()
    total = int(r[2] or 0)
    with_e = int(r[0] or 0)
    return {
        "period_hours": period_hours,
        "with_evidence": with_e,
        "without_evidence": int(r[1] or 0),
        "total": total,
        "rate_pct": round(100.0 * with_e / total, 2) if total > 0 else 0.0,
    }
```

- [ ] **Step 5: Register router in app.py**

Edit `web_cabinet/app.py`. Find the block around line 175–177 with router imports:

```python
from .api_boundary_v1 import router as api_boundary_v1_router
from .analytics_v1 import router as analytics_v1_router
```

Add immediately after:
```python
from .admin.ai_observability import router as admin_ai_obs_router
```

Find the block around line 655–657:
```python
app.include_router(auth_boundary_v1_router)
app.include_router(api_boundary_v1_router)
app.include_router(analytics_v1_router)
```

Add immediately after:
```python
app.include_router(admin_ai_obs_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/web_cabinet/admin/test_ai_observability.py -v`
Expected: 6 passed.

- [ ] **Step 7: Run pytest CI gate locally**

Run: `bash scripts/run_ci_gate.sh 2>&1 | tail -20`
Expected: pytest gate green; no new warnings.

- [ ] **Step 8: Commit backend**

```bash
git add web_cabinet/ai/pricing.py web_cabinet/ai/call_log.py web_cabinet/ai/client.py \
        web_cabinet/admin/__init__.py web_cabinet/admin/ai_observability.py \
        web_cabinet/app.py \
        tests/web_cabinet/ai/test_pricing.py tests/web_cabinet/ai/test_call_log_persistence.py \
        tests/web_cabinet/admin/__init__.py tests/web_cabinet/admin/test_ai_observability.py
git commit -m "$(cat <<'EOF'
feat(P0-1): backend for /admin/ai observability dashboard

Add 4 endpoints under /api/admin/ai/* (stats, calls, calls/{id},
grounding-rate) gated by audit.view. Best-effort persistence into
ai_call_log from AnthropicClient._log_call (sync, swallows DB errors).
Static Anthropic pricing module (sonnet/opus/haiku 4.x, verified 2026-05).
50KB cap on prompt/response with TRUNCATED marker.

Verified: 16 unit + endpoint tests green via TestClient against test PG.

Spec: docs/superpowers/specs/2026-05-09-p0-1-ai-observability-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Frontend (commit 3)

### Task 3.1: Next.js API proxy routes for /api/admin/ai/*

**Files:**
- Create: `web_app/app/api/admin/ai/stats/route.ts`
- Create: `web_app/app/api/admin/ai/calls/route.ts`
- Create: `web_app/app/api/admin/ai/calls/[callId]/route.ts`
- Create: `web_app/app/api/admin/ai/grounding-rate/route.ts`

- [ ] **Step 1: Create stats proxy**

Path: `web_app/app/api/admin/ai/stats/route.ts`

```typescript
import { NextResponse } from 'next/server';
import { backendFetch } from '@/lib/server/backend';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const upstream = await backendFetch(`/api/admin/ai/stats${qs ? `?${qs}` : ''}`);
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') || 'application/json' },
  });
}
```

- [ ] **Step 2: Create calls list proxy**

Path: `web_app/app/api/admin/ai/calls/route.ts`

```typescript
import { NextResponse } from 'next/server';
import { backendFetch } from '@/lib/server/backend';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const upstream = await backendFetch(`/api/admin/ai/calls${qs ? `?${qs}` : ''}`);
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') || 'application/json' },
  });
}
```

- [ ] **Step 3: Create call detail proxy**

Path: `web_app/app/api/admin/ai/calls/[callId]/route.ts`

```typescript
import { NextResponse } from 'next/server';
import { backendFetch } from '@/lib/server/backend';

export async function GET(_request: Request, { params }: { params: Promise<{ callId: string }> }) {
  const { callId } = await params;
  const upstream = await backendFetch(`/api/admin/ai/calls/${encodeURIComponent(callId)}`);
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') || 'application/json' },
  });
}
```

- [ ] **Step 4: Create grounding-rate proxy**

Path: `web_app/app/api/admin/ai/grounding-rate/route.ts`

```typescript
import { NextResponse } from 'next/server';
import { backendFetch } from '@/lib/server/backend';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const upstream = await backendFetch(`/api/admin/ai/grounding-rate${qs ? `?${qs}` : ''}`);
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') || 'application/json' },
  });
}
```

---

### Task 3.2: Typed API client `lib/api/admin-ai.ts`

**Files:**
- Create: `web_app/lib/api/admin-ai.ts`

- [ ] **Step 1: Create the client**

Path: `web_app/lib/api/admin-ai.ts`

```typescript
export type AiStats = {
  period_hours: number;
  count: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  error_count: number;
  error_rate: number;
};

export type AiCallRow = {
  id: number;
  created_at: string;
  endpoint: string;
  model: string;
  user_id: string | null;
  latency_ms: number;
  total_tokens: number;
  cost_usd: number;
  has_error: boolean;
};

export type AiCallDetail = AiCallRow & {
  task_type: string;
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  error: string | null;
  prompt: string | null;
  response: string | null;
  evidence_chips: string[] | null;
  tools_used: Array<Record<string, unknown>> | null;
};

export type GroundingRate = {
  period_hours: number;
  with_evidence: number;
  without_evidence: number;
  total: number;
  rate_pct: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'include' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error(`request failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export function fetchAiStats(periodHours: 1 | 24 | 168 = 24): Promise<AiStats> {
  return getJson<AiStats>(`/api/admin/ai/stats?period_hours=${periodHours}`);
}

export function fetchAiCalls(opts: { limit?: number; endpoint?: string; userId?: string; status?: 'ok' | 'error' } = {}): Promise<AiCallRow[]> {
  const sp = new URLSearchParams();
  if (opts.limit) sp.set('limit', String(opts.limit));
  if (opts.endpoint) sp.set('endpoint', opts.endpoint);
  if (opts.userId) sp.set('user_id', opts.userId);
  if (opts.status) sp.set('status', opts.status);
  const qs = sp.toString();
  return getJson<AiCallRow[]>(`/api/admin/ai/calls${qs ? `?${qs}` : ''}`);
}

export function fetchAiCallDetail(callId: number): Promise<AiCallDetail> {
  return getJson<AiCallDetail>(`/api/admin/ai/calls/${callId}`);
}

export function fetchGroundingRate(periodHours: 1 | 24 | 168 = 24): Promise<GroundingRate> {
  return getJson<GroundingRate>(`/api/admin/ai/grounding-rate?period_hours=${periodHours}`);
}

export async function triggerMorningBrief(): Promise<void> {
  const res = await fetch('/api/ai/morning-brief', { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error(`morning-brief failed: ${res.status}`);
}

export async function triggerInsightsScan(): Promise<void> {
  const res = await fetch('/api/ai/insights/scan-now', { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error(`insights scan failed: ${res.status}`);
}
```

---

### Task 3.3: Trace drawer component

**Files:**
- Create: `web_app/components/admin/ai-call-trace-drawer.tsx`

- [ ] **Step 1: Create the drawer**

Path: `web_app/components/admin/ai-call-trace-drawer.tsx`

```tsx
'use client';
import { useEffect, useState } from 'react';
import { fetchAiCallDetail, type AiCallDetail } from '@/lib/api/admin-ai';

type Props = { callId: number | null; onClose: () => void };

export function AiCallTraceDrawer({ callId, onClose }: Props) {
  const [detail, setDetail] = useState<AiCallDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (callId == null) return;
    setDetail(null); setError(null);
    let active = true;
    fetchAiCallDetail(callId).then((d) => { if (active) setDetail(d); }).catch((e) => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [callId]);

  if (callId == null) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-header">
          <h3>Trace #{callId}</h3>
          <button onClick={onClose} aria-label="Закрыть">✕</button>
        </header>
        <div className="drawer-body">
          {error && <div className="error-text">Ошибка загрузки: {error}</div>}
          {!detail && !error && <div className="muted">Загрузка…</div>}
          {detail && (
            <>
              <div className="grid grid-3">
                <div><div className="muted">Latency</div><div>{detail.latency_ms} мс</div></div>
                <div><div className="muted">Токены</div><div>{detail.input_tokens + detail.output_tokens}</div></div>
                <div><div className="muted">Стоимость</div><div>${detail.cost_usd.toFixed(4)}</div></div>
              </div>
              <h4>Endpoint / model</h4>
              <p className="mono">{detail.endpoint} · {detail.model} · {detail.task_type}</p>
              {detail.error && (<><h4>Ошибка</h4><pre className="error-text">{detail.error}</pre></>)}
              <h4>Prompt</h4>
              <pre className="trace-pre">{detail.prompt ?? '—'}</pre>
              <h4>Response</h4>
              <pre className="trace-pre">{detail.response ?? '—'}</pre>
              <h4>Evidence chips</h4>
              {detail.evidence_chips && detail.evidence_chips.length > 0 ? (
                <ul>{detail.evidence_chips.map((c, i) => <li key={i}>{c}</li>)}</ul>
              ) : <p className="muted">— нет evidence —</p>}
              <h4>Tools used</h4>
              {detail.tools_used && detail.tools_used.length > 0 ? (
                <pre className="trace-pre">{JSON.stringify(detail.tools_used, null, 2)}</pre>
              ) : <p className="muted">— инструменты не вызывались —</p>}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
```

---

### Task 3.4: Main observability component

**Files:**
- Create: `web_app/components/admin/ai-observability.tsx`

- [ ] **Step 1: Create the page component**

Path: `web_app/components/admin/ai-observability.tsx`

```tsx
'use client';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import {
  fetchAiStats, fetchAiCalls, fetchGroundingRate,
  triggerMorningBrief, triggerInsightsScan,
  type AiStats, type AiCallRow, type GroundingRate,
} from '@/lib/api/admin-ai';
import { AiCallTraceDrawer } from './ai-call-trace-drawer';

type Period = 1 | 24 | 168;
const PERIOD_LABEL: Record<Period, string> = { 1: '1 ч', 24: '24 ч', 168: '7 дн' };

export function AiObservability() {
  const [period, setPeriod] = useState<Period>(24);
  const [stats, setStats] = useState<AiStats | null>(null);
  const [grounding, setGrounding] = useState<GroundingRate | null>(null);
  const [calls, setCalls] = useState<AiCallRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openCallId, setOpenCallId] = useState<number | null>(null);
  const [triggerBusy, setTriggerBusy] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([
      fetchAiStats(period),
      fetchGroundingRate(period),
      fetchAiCalls({ limit: 100 }),
    ]).then(([s, g, c]) => {
      if (!active) return;
      setStats(s); setGrounding(g); setCalls(c);
    }).catch((e) => {
      if (!active) return;
      setError(e instanceof Error && e.message === 'forbidden' ? 'Нет прав доступа' : String(e));
    });
    return () => { active = false; };
  }, [period, reloadKey]);

  async function handleTrigger(name: 'morning' | 'scan') {
    setTriggerBusy(name);
    try {
      if (name === 'morning') await triggerMorningBrief();
      else await triggerInsightsScan();
      setReloadKey((k) => k + 1);
    } catch (e) {
      setError(`Триггер ${name} провалился: ${e}`);
    } finally {
      setTriggerBusy(null);
    }
  }

  if (error === 'Нет прав доступа') {
    return <div className="card error-text">Нет прав доступа</div>;
  }

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">AI-наблюдаемость</h1>
          <p className="page-subtitle">Сводка вызовов LLM, grounding rate и trace отдельных вызовов.</p>
        </div>
        <div className="period-tabs">
          {([1, 24, 168] as Period[]).map((p) => (
            <button
              key={p}
              className={p === period ? 'period-tab active' : 'period-tab'}
              onClick={() => setPeriod(p)}
            >{PERIOD_LABEL[p]}</button>
          ))}
        </div>
      </div>

      {error && <div className="card error-text">{error}</div>}

      <div className="grid grid-4">
        <MetricCard title={`Вызовов за ${PERIOD_LABEL[period]}`} value={stats?.count ?? '—'} />
        <MetricCard title="p95 латентность" value={stats ? `${(stats.p95_latency_ms / 1000).toFixed(1)} с` : '—'} />
        <MetricCard title="Токенов всего" value={stats ? stats.total_tokens.toLocaleString('ru-RU') : '—'} />
        <MetricCard title="Стоимость" value={stats ? `$${stats.total_cost_usd.toFixed(2)}` : '—'} />
      </div>

      <div className="grid grid-2">
        <Card>
          <h3 className="card-title">Grounding rate</h3>
          {grounding ? (
            <>
              <div className="big-number">{grounding.rate_pct.toFixed(1)}%</div>
              <p className="small-muted">{grounding.with_evidence} из {grounding.total} с evidence</p>
            </>
          ) : <p className="muted">—</p>}
        </Card>

        <Card>
          <h3 className="card-title">Ручные триггеры</h3>
          <div className="action-row">
            <button
              data-testid="trigger-morning-brief"
              disabled={triggerBusy !== null}
              onClick={() => handleTrigger('morning')}
            >
              {triggerBusy === 'morning' ? 'Генерация…' : 'Сгенерировать утренний брифинг'}
            </button>
            <button
              data-testid="trigger-insights-scan"
              disabled={triggerBusy !== null}
              onClick={() => handleTrigger('scan')}
            >
              {triggerBusy === 'scan' ? 'Сканирование…' : 'Сканировать инсайты сейчас'}
            </button>
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="card-title">Последние 100 вызовов</h3>
        <DataTable
          rows={calls as unknown as Record<string, unknown>[]}
          columns={[
            { key: 'id', header: 'ID', render: (r) => String((r as AiCallRow).id) },
            { key: 'created_at', header: 'Время', render: (r) => new Date((r as AiCallRow).created_at).toLocaleString('ru-RU') },
            { key: 'endpoint', header: 'Endpoint', render: (r) => (r as AiCallRow).endpoint },
            { key: 'model', header: 'Модель', render: (r) => (r as AiCallRow).model.replace('claude-', '') },
            { key: 'latency_ms', header: 'Latency', render: (r) => `${((r as AiCallRow).latency_ms / 1000).toFixed(1)} с` },
            { key: 'total_tokens', header: 'Токенов', render: (r) => String((r as AiCallRow).total_tokens) },
            { key: 'cost_usd', header: 'Стоимость', render: (r) => `$${(r as AiCallRow).cost_usd.toFixed(4)}` },
            { key: 'has_error', header: 'Статус', render: (r) => (r as AiCallRow).has_error ? '✗' : '✓' },
          ]}
          onRowClick={(row) => setOpenCallId((row as unknown as AiCallRow).id)}
        />
      </Card>

      <AiCallTraceDrawer callId={openCallId} onClose={() => setOpenCallId(null)} />
    </div>
  );
}
```

- [ ] **Step 2: Verify DataTable supports `onRowClick`**

Run: `grep -n "onRowClick\|interface DataTable" web_app/components/ui/data-table.tsx | head`

If `onRowClick` is missing, add it as optional prop:

```typescript
type DataTableProps = {
  rows: Record<string, unknown>[];
  columns: Array<{ key: string; header: string; render: (row: Record<string, unknown>) => React.ReactNode }>;
  onRowClick?: (row: Record<string, unknown>) => void;
};
```

And in the row render: `<tr onClick={() => onRowClick?.(row)} className={onRowClick ? 'clickable' : undefined}>`.

If DataTable already supports it, skip this step.

---

### Task 3.5: Page entry at /admin/ai

**Files:**
- Create: `web_app/app/(protected)/admin/ai/page.tsx`

- [ ] **Step 1: Create page**

Path: `web_app/app/(protected)/admin/ai/page.tsx`

```tsx
import { AiObservability } from '@/components/admin/ai-observability';

export default function AdminAiPage() {
  return <AiObservability />;
}
```

---

### Task 3.6: Link from Admin Command Center

**Files:**
- Modify: `web_app/components/extended/admin-command-center.tsx`

- [ ] **Step 1: Add link to "AI-наблюдаемость" in Admin flows card**

Edit `web_app/components/extended/admin-command-center.tsx`. Find:
```tsx
<div className="linked-inline-actions">
  <Link href="/observability">Observability</Link>
  <Link href="/support">Support</Link>
  <Link href="/pilot">Pilot</Link>
  <Link href="/readiness">Readiness</Link>
</div>
```

Replace with:
```tsx
<div className="linked-inline-actions">
  <Link href="/admin/ai">AI-наблюдаемость</Link>
  <Link href="/observability">Observability</Link>
  <Link href="/support">Support</Link>
  <Link href="/pilot">Pilot</Link>
  <Link href="/readiness">Readiness</Link>
</div>
```

---

### Task 3.7: Minimal styling

**Files:**
- Modify: `web_app/app/globals.css` (or the relevant style sheet — verify path)

- [ ] **Step 1: Locate global stylesheet**

Run: `find web_app -name "globals.css" -o -name "app.css" | head -3`

- [ ] **Step 2: Append styles**

Append to whichever global stylesheet handles `.card`, `.topbar`, etc:

```css
.period-tabs { display: flex; gap: 4px; }
.period-tab { padding: 6px 12px; border: 1px solid #ddd; background: #fff; cursor: pointer; }
.period-tab.active { background: #1a73e8; color: #fff; border-color: #1a73e8; }
.action-row { display: flex; gap: 12px; flex-wrap: wrap; }
.action-row button { padding: 8px 16px; border: 1px solid #1a73e8; background: #1a73e8; color: #fff; cursor: pointer; }
.action-row button:disabled { opacity: 0.6; cursor: wait; }
.big-number { font-size: 48px; font-weight: 600; }
.drawer-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000; }
.drawer { position: fixed; right: 0; top: 0; bottom: 0; width: min(640px, 90vw); background: #fff; overflow-y: auto; box-shadow: -2px 0 16px rgba(0,0,0,0.2); }
.drawer-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid #eee; }
.drawer-body { padding: 16px; }
.trace-pre { background: #f5f5f5; padding: 12px; border-radius: 4px; max-height: 320px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
.mono { font-family: ui-monospace, monospace; }
```

---

### Task 3.8: Playwright e2e proof

**Files:**
- Create: `web_app/e2e/admin-ai.spec.ts`

- [ ] **Step 1: Verify Playwright base config exists**

Run: `ls web_app/playwright.config.* web_app/e2e/ 2>/dev/null`

If no Playwright config exists yet, skip this task — fall back to manual MCP browser proof in Task 4 (capture screenshots via mcp__playwright__browser tools instead).

If Playwright is configured, continue.

- [ ] **Step 2: Write e2e spec**

Path: `web_app/e2e/admin-ai.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

test.describe('/admin/ai dashboard', () => {
  test('admin sees stats, triggers brief, opens trace', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name=username]', 'admin');
    await page.fill('input[name=password]', 'admin');
    await page.click('button[type=submit]');
    await page.waitForURL('**/dashboard');

    await page.goto('/admin/ai');
    await expect(page.getByRole('heading', { name: /AI-наблюдаемость/i })).toBeVisible();

    await page.getByTestId('trigger-morning-brief').click();
    await page.waitForResponse((r) => r.url().includes('/api/ai/morning-brief') && r.status() === 200, { timeout: 60000 });

    await page.reload();
    await expect(page.getByText(/Вызовов за 24 ч/i)).toBeVisible();

    const firstRow = page.locator('table tr').nth(1);
    await firstRow.click();
    await expect(page.getByText(/^Trace #/)).toBeVisible();

    await page.screenshot({ path: 'admin_ai_dashboard.png', fullPage: true });
  });

  test('non-admin gets forbidden', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name=username]', 'farmer');
    await page.fill('input[name=password]', 'farmer');
    await page.click('button[type=submit]');
    await page.waitForURL(/.*/);

    await page.goto('/admin/ai');
    await expect(page.getByText(/Нет прав доступа/i)).toBeVisible();
  });
});
```

- [ ] **Step 3: Run e2e**

Run: `cd web_app && npx playwright test e2e/admin-ai.spec.ts --reporter=list`
Expected: 2 passed; `admin_ai_dashboard.png` created.

If "farmer" user does not exist in test fixtures, create it via API in test setup OR replace the negative test with a `mcp__playwright__browser` manual session in Task 4.

- [ ] **Step 4: Move screenshot into repo**

```bash
mkdir -p docs/iterations/proof_assets
mv web_app/admin_ai_dashboard.png docs/iterations/proof_assets/p0-1_admin_ai_dashboard.png
```

---

### Task 3.9: Commit frontend

- [ ] **Step 1: Run TS build to verify**

```bash
cd web_app && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 2: Commit**

```bash
git add web_app/app/api/admin/ai \
        web_app/app/\(protected\)/admin/ai \
        web_app/components/admin \
        web_app/components/extended/admin-command-center.tsx \
        web_app/lib/api/admin-ai.ts \
        web_app/app/globals.css \
        web_app/e2e/admin-ai.spec.ts \
        docs/iterations/proof_assets/p0-1_admin_ai_dashboard.png
git commit -m "$(cat <<'EOF'
feat(P0-1): /admin/ai observability dashboard UI

Russian UI with 5 widgets: 4 stat cards (count/p95/tokens/cost),
grounding-rate panel, manual trigger buttons, last-100-calls table
with click-to-open trace drawer (prompt/response/evidence/tools).
Period selector 1h/24h/7d. Forbidden state for non-Admin users.
Next.js proxy routes under /api/admin/ai/*. Playwright e2e proof.

Spec: docs/superpowers/specs/2026-05-09-p0-1-ai-observability-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Verification

### Task 4.1: Run all 7 CI gates

- [ ] **Step 1: pytest gate**

```bash
mkdir -p artifacts/_ci
bash scripts/run_ci_gate.sh 2>&1 | tee artifacts/_ci/p0-1_pytest_gate.log
```
Expected: green.

- [ ] **Step 2: web smoke**

```bash
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json artifacts/_ci/p0-1_web_smoke.json | tee artifacts/_ci/p0-1_web_smoke.log
```
Expected: all smoke endpoints HTTP 200.

- [ ] **Step 3: golden verify_refactor**

```bash
python -m genomeai.cli verify_refactor --project-root . --golden golden \
  --report-root artifacts/_ci/p0-1_verify_refactor | tee artifacts/_ci/p0-1_verify_refactor.log
```
Expected: 0 diffs.

- [ ] **Step 4: warning governance**

```bash
bash scripts/run_warning_governance_gate.sh 2>&1 | tee artifacts/_ci/p0-1_warnings.log
```
Expected: green; no new unaccounted warnings.

- [ ] **Step 5: operational rollout**

```bash
bash scripts/run_operational_rollout_gate.sh 2>&1 | tee artifacts/_ci/p0-1_rollout.log
```
Expected: green.

- [ ] **Step 6: competitive acceptance**

```bash
bash scripts/run_competitive_acceptance_gate.sh 2>&1 | tee artifacts/_ci/p0-1_competitive.log
```
Expected: green.

- [ ] **Step 7: performance gates**

```bash
bash scripts/run_perf_gates.sh 2>&1 | tee artifacts/_ci/p0-1_perf.log
```
Expected: green; specifically `/api/admin/ai/stats` p50 < 200 ms.

If any gate fails, fix and re-run only the failed gate before continuing.

---

### Task 4.2: Write proof file

**Files:**
- Create: `docs/iterations/T34-P0-1_execution_proof.md`

- [ ] **Step 1: Create the proof file**

Path: `docs/iterations/T34-P0-1_execution_proof.md`

```markdown
# T34-P0-1 Execution Proof — AI Observability Admin Panel

**Date:** 2026-05-09
**Source brief:** docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md §P0-1
**Spec:** docs/superpowers/specs/2026-05-09-p0-1-ai-observability-design.md
**Plan:** docs/superpowers/plans/2026-05-09-p0-1-ai-observability.md
**Commits:** <fill from git log>

## Scope

Implement /admin/ai dashboard for the Admin role: 4 stat cards, grounding
rate, manual triggers (morning-brief, insights/scan-now), last-100-calls
table with trace drawer. Backend: 4 endpoints under /api/admin/ai/* and
best-effort persistence into ai_call_log.

## Executed checks

| # | Check | Result | Artifact |
|---|---|---|---|
| 1 | alembic upgrade/downgrade/upgrade | <fill> | console output |
| 2 | pytest gate | <fill> | artifacts/_ci/p0-1_pytest_gate.log |
| 3 | web smoke | <fill> | artifacts/_ci/p0-1_web_smoke.log |
| 4 | verify_refactor (golden) | <fill> | artifacts/_ci/p0-1_verify_refactor.log |
| 5 | warning governance | <fill> | artifacts/_ci/p0-1_warnings.log |
| 6 | operational rollout | <fill> | artifacts/_ci/p0-1_rollout.log |
| 7 | competitive acceptance | <fill> | artifacts/_ci/p0-1_competitive.log |
| 8 | perf gates (p50 stats <200ms) | <fill> | artifacts/_ci/p0-1_perf.log |
| 9 | Playwright admin happy path | <fill> | docs/iterations/proof_assets/p0-1_admin_ai_dashboard.png |
| 10 | Playwright non-admin 403 | <fill> | <screenshot or test log> |

## Acceptance criteria from brief

- [x] Login admin/admin, /admin/ai, non-empty stats after morning-brief — <fill yes/no, screenshot ref>
- [x] Non-Admin returns 403 — <fill>
- [x] admin_ai_dashboard.png in commit — <fill>
- [x] /api/admin/ai/stats p50 <200ms — <fill from perf log>

## Net result

<fill: number of new files, lines, tests, gates green; list any deferred items>

## Honest status

`proven` / `partially_proven` / `not_proven` — choose based on actual gate results.
If `partially_proven`, list what is and is not proven.
```

- [ ] **Step 2: Fill in actual results**

Replace each `<fill>` with the actual output from gate logs and screenshots.

- [ ] **Step 3: Commit proof**

```bash
git add docs/iterations/T34-P0-1_execution_proof.md artifacts/_ci/p0-1_*.log artifacts/_ci/p0-1_*.json
git commit -m "$(cat <<'EOF'
docs(P0-1): execution proof for AI observability admin panel

All 7 CI gates run and recorded with artifact paths. Acceptance bar from
THESIS_ALIGNMENT_BRIEF_2026-05-08.md §P0-1 met: admin can see live LLM
call telemetry, click trace, trigger morning-brief / scan-now; non-admin
blocked. Endpoint /api/admin/ai/stats p50 measured.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

> Note: `artifacts/_ci/` is normally gitignored per CLAUDE.md §11. If it is, attach logs to the proof file via inline excerpts instead of committing the raw artifact files. Verify with `cat .gitignore | grep artifacts` before staging.

---

## Self-Review

**Spec coverage:**
- Migration ai_call_log → Task 1.1 ✓
- Pricing module → Task 2.1 ✓
- Best-effort logging hook → Task 2.2, 2.3 ✓
- 4 backend endpoints → Task 2.4 ✓
- Frontend page + 5 widgets → Tasks 3.1–3.7 ✓
- 403 for non-Admin → Task 3.4 (frontend message), enforced by `require_permissions("audit.view")` in 2.4 ✓
- Playwright proof → Task 3.8 ✓
- 3-commit strategy → Tasks 1.1, 2.7, 3.9 ✓
- 7 gates + proof → Tasks 4.1, 4.2 ✓

**Placeholder scan:** No TBDs / TODOs / "implement later" inside steps. Step 4.2 has `<fill>` placeholders but those are template fields the engineer must fill in *during execution*, not lazy plan placeholders — they are acceptable in proof files per CLAUDE.md format.

**Type consistency:** `AiStats`, `AiCallRow`, `AiCallDetail`, `GroundingRate` defined in Task 3.2 are referenced in Tasks 3.3 and 3.4 — consistent. Backend response shapes in Task 2.4 match the frontend types one-to-one.
