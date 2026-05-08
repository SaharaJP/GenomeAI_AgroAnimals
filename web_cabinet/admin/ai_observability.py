"""Admin AI observability — /api/admin/ai/* endpoints."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..ai.models import (
    AICallDetailResponse,
    AICallRow,
    AICallStatsResponse,
    AIGroundingRateResponse,
)
from ..auth import get_db
from ..rbac import require_permissions

logger = logging.getLogger("genomeai.admin.ai_observability")

router = APIRouter(prefix="/api/admin/ai", tags=["admin-ai-observability"])

_ALLOWED_PERIODS = (1, 24, 168)


def _validate_period(period_hours: int) -> int:
    if period_hours not in _ALLOWED_PERIODS:
        raise HTTPException(status_code=400, detail={"error": "invalid_period", "allowed": list(_ALLOWED_PERIODS)})
    return period_hours


# compat: psycopg cursor-factory shim — connect_postgres_compat() does not
# pin a row factory, so cursors may yield tuple rows or dict rows depending
# on caller. Once a project-wide row factory is set on connect, delete this
# helper and revert to direct indexing. Internal to this module — not a
# public API contract; no entry in deprecation_policy.json required.
def _row_get(row, idx: int, key: str):
    """Compatibility shim: psycopg dict_row vs tuple_row."""
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[idx]
    except (IndexError, TypeError):
        return None


@router.get("/stats", response_model=AICallStatsResponse)
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
    count = int(_row_get(row, 0, "count") or 0)
    errors = int(_row_get(row, 6, "errors") or 0)
    return {
        "period_hours": period_hours,
        "count": count,
        "p50_latency_ms": int(_row_get(row, 1, "p50") or 0),
        "p95_latency_ms": int(_row_get(row, 2, "p95") or 0),
        "total_input_tokens": int(_row_get(row, 3, "total_input") or 0),
        "total_output_tokens": int(_row_get(row, 4, "total_output") or 0),
        "total_tokens": int(_row_get(row, 3, "total_input") or 0) + int(_row_get(row, 4, "total_output") or 0),
        "total_cost_usd": float(_row_get(row, 5, "total_cost") or 0),
        "error_count": errors,
        "error_rate": (errors / count) if count > 0 else 0.0,
    }


@router.get("/calls", response_model=list[AICallRow])
def calls(
    limit: int = Query(100, ge=1, le=500),
    endpoint: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(ok|error)$"),
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
    out = []
    for r in rows:
        out.append({
            "id": _row_get(r, 0, "id"),
            "created_at": (_row_get(r, 1, "created_at") or None) and _row_get(r, 1, "created_at").isoformat(),
            "endpoint": _row_get(r, 2, "endpoint"),
            "model": _row_get(r, 3, "model"),
            "user_id": _row_get(r, 4, "user_id"),
            "latency_ms": int(_row_get(r, 5, "latency_ms") or 0),
            "total_tokens": int(_row_get(r, 6, "total_tokens") or 0),
            "cost_usd": float(_row_get(r, 7, "cost_usd") or 0),
            "has_error": bool(_row_get(r, 8, "has_error")),
        })
    return out


@router.get("/calls/{call_id}", response_model=AICallDetailResponse)
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
        if value is None or isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return None

    return {
        "id": _row_get(r, 0, "id"),
        "created_at": (_row_get(r, 1, "created_at") or None) and _row_get(r, 1, "created_at").isoformat(),
        "user_id": _row_get(r, 2, "user_id"),
        "endpoint": _row_get(r, 3, "endpoint"),
        "task_type": _row_get(r, 4, "task_type"),
        "model": _row_get(r, 5, "model"),
        "input_tokens": int(_row_get(r, 6, "input_tokens") or 0),
        "output_tokens": int(_row_get(r, 7, "output_tokens") or 0),
        "cache_creation_tokens": int(_row_get(r, 8, "cache_creation_tokens") or 0),
        "cache_read_tokens": int(_row_get(r, 9, "cache_read_tokens") or 0),
        "cost_usd": float(_row_get(r, 10, "cost_usd") or 0),
        "latency_ms": int(_row_get(r, 11, "latency_ms") or 0),
        "error": _row_get(r, 12, "error"),
        "prompt": _row_get(r, 13, "prompt"),
        "response": _row_get(r, 14, "response"),
        "evidence_chips": _parse_json(_row_get(r, 15, "evidence_chips")),
        "tools_used": _parse_json(_row_get(r, 16, "tools_used")),
    }


@router.get("/grounding-rate", response_model=AIGroundingRateResponse)
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
    total = int(_row_get(r, 2, "total") or 0)
    with_e = int(_row_get(r, 0, "with_evidence") or 0)
    return {
        "period_hours": period_hours,
        "with_evidence": with_e,
        "without_evidence": int(_row_get(r, 1, "without_evidence") or 0),
        "total": total,
        "rate_pct": round(100.0 * with_e / total, 2) if total > 0 else 0.0,
    }
