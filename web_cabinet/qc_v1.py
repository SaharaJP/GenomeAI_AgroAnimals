"""DB-backed QC incidents boundary."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from packages.contracts.api_boundary_v1 import (
    QcIncident,
    QcIncidentsListResponse,
)
from web_cabinet.insights_v1 import _conn

logger = logging.getLogger("genomeai.web_cabinet.qc_v1")


def _dict_cursor(conn):
    """Return a dict-row cursor regardless of psycopg variant (mirrors insights_v1)."""
    try:
        from psycopg.rows import dict_row  # type: ignore
        return conn.cursor(row_factory=dict_row)
    except Exception:
        import psycopg2.extras  # type: ignore
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _row_to_item(row: dict[str, Any]) -> QcIncident:
    sensors = row.get("affected_sensors") or []
    if isinstance(sensors, str):
        try:
            sensors = json.loads(sensors)
        except Exception:
            sensors = []

    def _iso(v):
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    return QcIncident(
        incident_id=row["incident_id"],
        farm_id=row["farm_id"],
        metric_id=row["metric_id"],
        period_start=_iso(row.get("period_start")) or "",
        period_end=_iso(row.get("period_end")),
        detector_type=row.get("detector_type") or "",
        severity=row.get("severity") or "warn",
        affected_sensors=list(sensors) if sensors else [],
        ai_description=row.get("ai_description"),
        root_cause=row.get("root_cause"),
        status=row.get("status") or "active",
        detected_at=_iso(row.get("detected_at")) or "",
    )


def list_incidents(
    *,
    farm_id: str,
    metric_id: Optional[str] = None,
    active: bool = True,
) -> QcIncidentsListResponse:
    sql = ["SELECT * FROM qc_incidents WHERE farm_id = %s"]
    params: list[Any] = [farm_id]
    if metric_id:
        sql.append("AND metric_id = %s")
        params.append(metric_id)
    if active:
        sql.append("AND status = 'active'")
    sql.append("ORDER BY period_start DESC LIMIT 200")
    with _conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(" ".join(sql), params)
            rows = cur.fetchall()
    items = [_row_to_item(r) for r in rows]
    return QcIncidentsListResponse(total=len(items), items=items)


def get_incident(incident_id: str) -> Optional[QcIncident]:
    with _conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM qc_incidents WHERE incident_id = %s", (incident_id,))
            row = cur.fetchone()
    return _row_to_item(row) if row else None


def dismiss_incident(incident_id: str) -> bool:
    """Soft-dismiss; idempotent."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE qc_incidents SET status = 'dismissed', resolved_at = NOW() "
                "WHERE incident_id = %s",
                (incident_id,),
            )
        conn.commit()
    return True
