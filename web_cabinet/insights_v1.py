"""DB-backed insights boundary (replaces JSON-seeded legacy)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

try:  # psycopg v3 (preferred in this repo)
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
    _PG_VARIANT = 3
except Exception:  # pragma: no cover - fallback to psycopg2 if installed
    psycopg = None  # type: ignore
    dict_row = None  # type: ignore
    _PG_VARIANT = 0
    try:
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore
        _PG_VARIANT = 2
    except Exception:
        psycopg2 = None  # type: ignore

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
    """Open a Postgres connection. Caller is responsible for closing/commit."""
    dsn = _dsn()
    if not dsn:
        raise RuntimeError("GENOMEAI_DB_DSN not set")
    if _PG_VARIANT == 3:
        return psycopg.connect(dsn)  # type: ignore[union-attr]
    if _PG_VARIANT == 2:
        return psycopg2.connect(dsn)  # type: ignore[union-attr]
    raise RuntimeError("No psycopg driver available")


def _dict_cursor(conn):
    """Return a dict-row cursor regardless of psycopg variant."""
    if _PG_VARIANT == 3:
        return conn.cursor(row_factory=dict_row)  # type: ignore[arg-type]
    if _PG_VARIANT == 2:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # type: ignore[union-attr]
    raise RuntimeError("No psycopg driver available")


def _coerce_jsonish(value: Any) -> Any:
    """Decode value if it's a JSON-encoded string, else return as-is."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def _row_to_item(row: dict[str, Any]) -> InsightItem:
    payload = _coerce_jsonish(row.get("payload_json")) or {}
    if not isinstance(payload, dict):
        payload = {}

    recs_raw = row.get("recommendations")
    if recs_raw is None:
        recs_raw = payload.get("recommendations") or []
    recs_raw = _coerce_jsonish(recs_raw) if isinstance(recs_raw, str) else recs_raw
    if not isinstance(recs_raw, list):
        recs_raw = []
    recs = [
        InsightRecommendation(
            id=r.get("id", f"r{i+1}"),
            text=r.get("text") or r.get("action", ""),
            deadline=r.get("deadline"),
        )
        for i, r in enumerate(recs_raw)
        if isinstance(r, dict)
    ]

    animal_ids = row.get("animal_ids")
    if animal_ids is None:
        animal_ids = payload.get("animal_ids") or []
    animal_ids = _coerce_jsonish(animal_ids) if isinstance(animal_ids, str) else animal_ids
    if not isinstance(animal_ids, list):
        animal_ids = []

    chart_data = row.get("chart_data")
    if chart_data is None:
        chart_data = payload.get("chart_data") or []
    chart_data = _coerce_jsonish(chart_data) if isinstance(chart_data, str) else chart_data
    if not isinstance(chart_data, list):
        chart_data = []

    edited_at_val = row.get("edited_at")
    edited_at_iso: Optional[str]
    if edited_at_val is None:
        edited_at_iso = None
    elif hasattr(edited_at_val, "isoformat"):
        edited_at_iso = edited_at_val.isoformat()
    else:
        edited_at_iso = str(edited_at_val)

    generated_at = row.get("generated_at_utc") or ""
    date_part = generated_at.split("T")[0] if isinstance(generated_at, str) and generated_at else ""

    return InsightItem(
        insight_id=row["insight_id"],
        type=payload.get("type", row.get("category") or "production"),
        severity=row.get("severity") or row.get("priority") or 'info',
        status=row.get("status") or 'to_check',
        date=date_part,
        animal_ids=[str(a) for a in animal_ids],
        title=row.get("title") or "",
        body=row.get("body") or payload.get("body") or "",
        action=row.get("action") or payload.get("action") or "",
        tags=payload.get("tags", []) if isinstance(payload.get("tags", []), list) else [],
        farm_id=row.get("farm_id"),
        farm_label=payload.get("farm_label"),
        farm_pct=payload.get("farm_pct"),
        holding_pct=payload.get("holding_pct"),
        chart_data=[float(x) for x in chart_data if isinstance(x, (int, float))],
        chart_label=payload.get("chart_label"),
        chart_unit=payload.get("chart_unit"),
        recommendations=recs,
        edited_at=edited_at_iso,
        edited_by=row.get("edited_by"),
        created_at=generated_at if isinstance(generated_at, str) else None,
        updated_at=edited_at_iso or (generated_at if isinstance(generated_at, str) else None),
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

    conn = _conn()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    items = [_row_to_item(r) for r in rows]
    if eff_min:
        items = [i for i in items if _SEVERITY_RANK.get(i.severity, 0) >= min_rank]
    return InsightsListResponse(total=len(items), items=items)


def get_insight(insight_id: str) -> Optional[InsightItem]:
    conn = _conn()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(
                "SELECT * FROM scanner_insights WHERE insight_id = %s AND deleted_at IS NULL",
                (insight_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
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
    sets: list[str] = []
    params: list[Any] = []
    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if body is not None:
        sets.append("body = %s")
        params.append(body)
    if action is not None:
        sets.append("action = %s")
        params.append(action)
    if recommendations is not None:
        sets.append("recommendations = %s::jsonb")
        params.append(json.dumps(recommendations))
    if not sets:
        return get_insight(insight_id)
    sets.append("edited_at = NOW()")
    sets.append("edited_by = %s")
    params.append(edited_by or 'unknown')
    params.append(insight_id)

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE scanner_insights SET {', '.join(sets)} "
                f"WHERE insight_id = %s AND deleted_at IS NULL",
                params,
            )
            updated = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    if updated == 0:
        return None
    return get_insight(insight_id)


def delete_insight(insight_id: str) -> bool:
    """Soft delete; idempotent."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scanner_insights SET deleted_at = NOW(), status = 'deleted' "
                "WHERE insight_id = %s",
                (insight_id,),
            )
        conn.commit()
    finally:
        conn.close()
    return True


def transition_insight(insight_id: str, new_status: str) -> Optional[InsightItem]:
    if new_status not in {'to_check', 'to_follow_up', 'done'}:
        return None
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scanner_insights SET status = %s "
                "WHERE insight_id = %s AND deleted_at IS NULL",
                (new_status, insight_id),
            )
            updated = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    if updated == 0:
        return None
    return get_insight(insight_id)


def get_settings(*, user_id: str, farm_id: str) -> InsightSettings:
    conn = _conn()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(
                "SELECT min_severity, enabled_categories FROM insight_settings "
                "WHERE user_id = %s AND farm_id = %s",
                (user_id, farm_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return InsightSettings(
            min_severity='info',
            enabled_categories=list(_DEFAULT_CATEGORIES),
        )
    cats = row["enabled_categories"]
    if isinstance(cats, str):
        try:
            cats = json.loads(cats)
        except Exception:
            cats = None
    if not isinstance(cats, list):
        cats = list(_DEFAULT_CATEGORIES)
    return InsightSettings(
        min_severity=row["min_severity"] or 'info',
        enabled_categories=cats,
    )


def put_settings(*, user_id: str, farm_id: str, settings: InsightSettings) -> InsightSettings:
    conn = _conn()
    try:
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
    finally:
        conn.close()
    return settings
