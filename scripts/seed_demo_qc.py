#!/usr/bin/env python3
"""One-shot: seed synthetic QC incidents so /analytics has visible overlays.

Idempotent. Refuses on GENOMEAI_PROFILE=prod.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.getenv("GENOMEAI_PROFILE", "dev") == "prod":
    print("REFUSING: GENOMEAI_PROFILE=prod is forbidden for demo seed", file=sys.stderr)
    sys.exit(2)

# Make sure project root + src/ are importable.
# ROOT must come BEFORE src/ on sys.path so that the root web_cabinet/ package
# (which contains insights_v1.py) shadows the installed src/web_cabinet/.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from web_cabinet.insights_v1 import _conn
from web_cabinet.analytics.qc_ai_describer import describe_qc_incident

FARM_ID = os.getenv("GENOMEAI_DEMO_FARM_ID", "INV_FARM_001")


def main() -> int:
    # Anchor to start of today (UTC) so period_start is deterministic across
    # runs — the unique constraint (farm_id, metric_id, detector_type,
    # period_start) only protects us when the timestamp is stable.
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    incidents = [
        {
            "incident_id": f"qc_seed_gap_{uuid.uuid4().hex[:6]}",
            "metric_id": "milk_ecm",
            "period_start": today - timedelta(days=10),
            "period_end": today - timedelta(days=8),
            "detector_type": "gap",
            "severity": "warn",
            "affected_sensors": ["milk_meter_01"],
            "root_cause": "Пропуск данных надоев",
        },
        {
            "incident_id": f"qc_seed_stuck_{uuid.uuid4().hex[:6]}",
            "metric_id": "scc",
            "period_start": today - timedelta(days=14),
            "period_end": today - timedelta(days=7),
            "detector_type": "stuck",
            "severity": "warn",
            "affected_sensors": ["scc_meter_03"],
            "root_cause": "Залипание SCC-датчика",
        },
    ]
    inserted = 0
    with _conn() as conn:
        with conn.cursor() as cur:
            for inc in incidents:
                cur.execute(
                    """
                    INSERT INTO qc_incidents
                      (incident_id, farm_id, metric_id, period_start, period_end,
                       detector_type, severity, affected_sensors, root_cause)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (farm_id, metric_id, detector_type, period_start) DO NOTHING
                    """,
                    (
                        inc["incident_id"], FARM_ID, inc["metric_id"],
                        inc["period_start"], inc["period_end"],
                        inc["detector_type"], inc["severity"],
                        json.dumps(inc["affected_sensors"]),
                        inc["root_cause"],
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
        conn.commit()
    # Run AI describer (demo mode reads seeded JSON) for ALL active incidents lacking ai_description
    described = 0
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT incident_id FROM qc_incidents "
                "WHERE farm_id=%s AND ai_description IS NULL AND status='active'",
                (FARM_ID,),
            )
            ids = [r[0] for r in cur.fetchall()]
    for iid in ids:
        if describe_qc_incident(iid):
            described += 1
    print(f"seeded={inserted} skipped_existing={len(incidents)-inserted} described={described}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
