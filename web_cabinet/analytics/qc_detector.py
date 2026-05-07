"""Deterministic QC heuristics: gap, range, stuck, flatline + cron gate."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from packages.contracts.api_boundary_v1 import QcIncident
from web_cabinet.insights_v1 import _conn

logger = logging.getLogger("genomeai.analytics.qc_detector")

# Per-metric range thresholds (min, max). Out-of-range -> incident.
RANGE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "milk_kg": (0.0, 80.0),
    "scc_cells_ml": (0.0, 5_000_000.0),
}

GAP_DAYS = 1            # >=1 day skip in animal milkings counts as gap (24h+)
STUCK_DAYS = 7          # 7 consecutive days same value
FLATLINE_THRESHOLD = 0.50  # 50% of herd at zero on a day


def detect_qc_incidents(farm_id: str) -> list[QcIncident]:
    """Run all 4 heuristics, upsert into qc_incidents, return only newly created ones."""
    new_items: list[dict] = []
    new_items += _detect_gap(farm_id)
    new_items += _detect_range(farm_id)
    new_items += _detect_stuck(farm_id)
    new_items += _detect_flatline(farm_id)
    return _upsert(new_items, farm_id)


def cron_should_skip_qc_scan(farm_id: str) -> bool:
    """Returns True when no new milkings or timeline_events since last_scan_at."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_scan_at FROM qc_scan_state WHERE farm_id=%s",
                    (farm_id,),
                )
                row = cur.fetchone()
                last = row[0] if row else None
                if last is None:
                    return False  # never scanned -> always run
                last_text = last.isoformat() if hasattr(last, "isoformat") else str(last)
                # New milkings? created_at column is TIMESTAMPTZ.
                cur.execute(
                    "SELECT 1 FROM dm_milkings_daily "
                    "WHERE tenant_id=%s AND created_at > %s::timestamptz LIMIT 1",
                    (farm_id, last_text),
                )
                if cur.fetchone():
                    return False
                # New timeline events? created_at is TEXT (ISO 8601).
                cur.execute(
                    "SELECT 1 FROM timeline_events "
                    "WHERE tenant_id IN (%s, 'default') AND created_at > %s LIMIT 1",
                    (farm_id, last_text),
                )
                if cur.fetchone():
                    return False
        return True
    except Exception as exc:
        logger.warning(f"cron_should_skip_qc_scan failed: {exc}")
        return False  # fail open


def _record_scan(farm_id: str, *, skipped: bool, reason: Optional[str]) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO qc_scan_state (farm_id, last_scan_at, last_skipped_reason)
                    VALUES (%s, NOW(), %s)
                    ON CONFLICT (farm_id) DO UPDATE
                      SET last_scan_at = NOW(),
                          last_skipped_reason = EXCLUDED.last_skipped_reason
                    """,
                    (farm_id, reason if skipped else None),
                )
            conn.commit()
    except Exception as exc:
        logger.debug(f"_record_scan skipped: {exc}")


def _detect_gap(farm_id: str) -> list[dict]:
    """Find >=24h gaps in dm_milkings_daily per animal over last 14 days."""
    out: list[dict] = []
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT animal_id, date
                    FROM dm_milkings_daily
                    WHERE tenant_id=%s
                      AND date > (NOW() - INTERVAL '14 days')::date
                    ORDER BY animal_id, date
                    """,
                    (farm_id,),
                )
                rows = cur.fetchall()
        if not rows:
            return out
        from collections import defaultdict
        per_animal: dict[str, list] = defaultdict(list)
        for animal_id, d in rows:
            per_animal[animal_id].append(d)
        seen: set[tuple] = set()
        for animal_id, dates in per_animal.items():
            for i in range(1, len(dates)):
                if (dates[i] - dates[i - 1]).days > GAP_DAYS:
                    key = (dates[i - 1], dates[i])
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "metric_id": "milk_ecm",
                        "period_start": datetime.combine(dates[i - 1], datetime.min.time(), tzinfo=timezone.utc),
                        "period_end": datetime.combine(dates[i], datetime.min.time(), tzinfo=timezone.utc),
                        "detector_type": "gap",
                        "severity": "warn",
                        "affected_sensors": [animal_id],
                        "root_cause": f"Пропуск данных надоев у {animal_id}",
                    })
    except Exception as exc:
        logger.warning(f"_detect_gap failed: {exc}")
    return out


def _detect_range(farm_id: str) -> list[dict]:
    """Values outside thresholds -> range violation incident."""
    out: list[dict] = []
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT animal_id, date, milk_kg, scc_cells_ml
                    FROM dm_milkings_daily
                    WHERE tenant_id=%s
                      AND (milk_kg < %s OR milk_kg > %s
                           OR scc_cells_ml < %s OR scc_cells_ml > %s)
                      AND date > (NOW() - INTERVAL '14 days')::date
                    ORDER BY date
                    """,
                    (
                        farm_id,
                        RANGE_THRESHOLDS["milk_kg"][0],
                        RANGE_THRESHOLDS["milk_kg"][1],
                        RANGE_THRESHOLDS["scc_cells_ml"][0],
                        RANGE_THRESHOLDS["scc_cells_ml"][1],
                    ),
                )
                rows = cur.fetchall()
        if not rows:
            return out
        from collections import defaultdict
        bymetric: dict[str, list] = defaultdict(list)
        for animal_id, d, milk, scc in rows:
            mn, mx = RANGE_THRESHOLDS["milk_kg"]
            if milk is not None and (milk < mn or milk > mx):
                bymetric["milk_ecm"].append((animal_id, d))
            mn, mx = RANGE_THRESHOLDS["scc_cells_ml"]
            if scc is not None and (scc < mn or scc > mx):
                bymetric["scc"].append((animal_id, d))
        for metric_id, hits in bymetric.items():
            if not hits:
                continue
            ds = sorted({d for _, d in hits})
            ps, pe = ds[0], ds[-1]
            sensors = sorted({a for a, _ in hits})[:5]
            out.append({
                "metric_id": metric_id,
                "period_start": datetime.combine(ps, datetime.min.time(), tzinfo=timezone.utc),
                "period_end": datetime.combine(pe, datetime.min.time(), tzinfo=timezone.utc),
                "detector_type": "range",
                "severity": "high",
                "affected_sensors": sensors,
                "root_cause": f"Значения {metric_id} вне допустимого диапазона",
            })
    except Exception as exc:
        logger.warning(f"_detect_range failed: {exc}")
    return out


def _detect_stuck(farm_id: str) -> list[dict]:
    """Same SCC value for >=7 consecutive days -> stuck sensor."""
    out: list[dict] = []
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT animal_id, date, scc_cells_ml
                    FROM dm_milkings_daily
                    WHERE tenant_id=%s
                      AND date > (NOW() - INTERVAL '21 days')::date
                    ORDER BY animal_id, date
                    """,
                    (farm_id,),
                )
                rows = cur.fetchall()
        if not rows:
            return out
        from collections import defaultdict
        per_animal: dict[str, list] = defaultdict(list)
        for animal_id, d, scc in rows:
            per_animal[animal_id].append((d, scc))
        for animal_id, seq in per_animal.items():
            if len(seq) < STUCK_DAYS:
                continue
            run_start = seq[0][0]
            run_value = seq[0][1]
            run_len = 1
            emitted = False
            for i in range(1, len(seq)):
                if (
                    seq[i][1] == run_value
                    and (seq[i][0] - seq[i - 1][0]).days == 1
                ):
                    run_len += 1
                    if run_len >= STUCK_DAYS and not emitted:
                        out.append({
                            "metric_id": "scc",
                            "period_start": datetime.combine(run_start, datetime.min.time(), tzinfo=timezone.utc),
                            "period_end": datetime.combine(seq[i][0], datetime.min.time(), tzinfo=timezone.utc),
                            "detector_type": "stuck",
                            "severity": "warn",
                            "affected_sensors": [animal_id],
                            "root_cause": f"Одинаковое значение SCC {run_value} {run_len} дней подряд",
                        })
                        emitted = True
                else:
                    run_start = seq[i][0]
                    run_value = seq[i][1]
                    run_len = 1
                    emitted = False
    except Exception as exc:
        logger.warning(f"_detect_stuck failed: {exc}")
    return out


def _detect_flatline(farm_id: str) -> list[dict]:
    """Day where >=50% of herd has milk_kg=0 -> systemic outage."""
    out: list[dict] = []
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT date,
                           SUM(CASE WHEN milk_kg = 0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS pct_zero
                    FROM dm_milkings_daily
                    WHERE tenant_id=%s
                      AND date > (NOW() - INTERVAL '14 days')::date
                    GROUP BY 1
                    HAVING SUM(CASE WHEN milk_kg = 0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) >= %s
                    """,
                    (farm_id, FLATLINE_THRESHOLD),
                )
                rows = cur.fetchall()
        for d, pct in rows or []:
            out.append({
                "metric_id": "milk_ecm",
                "period_start": datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc),
                "period_end": datetime.combine(d, datetime.max.time(), tzinfo=timezone.utc),
                "detector_type": "flatline",
                "severity": "high",
                "affected_sensors": [],
                "root_cause": f"Массовый ноль надоев ({int(pct*100)}% коров)",
            })
    except Exception as exc:
        logger.warning(f"_detect_flatline failed: {exc}")
    return out


def _upsert(items: list[dict], farm_id: str) -> list[QcIncident]:
    """Insert with dedup on (farm_id, metric_id, detector_type, period_start)."""
    new_items: list[QcIncident] = []
    if not items:
        return new_items
    new_ids: list[str] = []
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                for item in items:
                    iid = f"qc_{uuid.uuid4().hex[:10]}"
                    cur.execute(
                        """
                        INSERT INTO qc_incidents
                          (incident_id, farm_id, metric_id, period_start, period_end,
                           detector_type, severity, affected_sensors, root_cause)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        ON CONFLICT (farm_id, metric_id, detector_type, period_start) DO NOTHING
                        RETURNING incident_id
                        """,
                        (
                            iid, farm_id, item["metric_id"],
                            item["period_start"], item.get("period_end"),
                            item["detector_type"], item.get("severity") or "warn",
                            json.dumps(item.get("affected_sensors") or []),
                            item.get("root_cause"),
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        new_ids.append(row[0])
            conn.commit()
        # Fetch full QcIncident objects AFTER commit (separate connection in qc_v1).
        if new_ids:
            from web_cabinet import qc_v1
            for nid in new_ids:
                full = qc_v1.get_incident(nid)
                if full:
                    new_items.append(full)
    except Exception as exc:
        logger.warning(f"_upsert failed: {exc}")
    return new_items


def run_qc_scan_for_all_farms() -> None:
    """Cron entry. Skips Claude-less detector when token-saver gate triggers."""
    try:
        from web_cabinet.ai.config import get_ai_settings
        farm_id = get_ai_settings().GENOMEAI_DEMO_FARM_ID
    except Exception as exc:
        logger.warning(f"run_qc_scan: cannot resolve farm_id: {exc}")
        return
    if cron_should_skip_qc_scan(farm_id):
        logger.info(f"qc_detector skipped: no new inputs farm={farm_id}")
        _record_scan(farm_id, skipped=True, reason="no_new_inputs")
        return
    new = detect_qc_incidents(farm_id)
    _record_scan(farm_id, skipped=False, reason=None)
    try:
        from web_cabinet.analytics.qc_ai_describer import describe_qc_incident
        for inc in new:
            describe_qc_incident(inc.incident_id)
    except Exception as exc:
        logger.debug(f"describe pass skipped: {exc}")
