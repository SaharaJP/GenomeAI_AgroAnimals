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
    # ~15 incidents across production / health / repro / behavior / feed / weather
    # so analytics overlays render on most tabs. Dedup is handled by the unique
    # (farm_id, metric_id, detector_type, period_start) constraint, so re-running
    # this seeder is idempotent.
    specs = [
        # Production tab
        ("milk_ecm", "gap", "warn", -10, -8, ["milk_meter_01"], "Пропуск данных надоев"),
        ("scc", "stuck", "warn", -14, -7, ["scc_meter_03"], "Залипание SCC-датчика"),
        ("scc", "range", "high", -8, -5, ["scc_meter_03"], "Средний SCC выше 350k — пересмотр гигиены"),
        ("fat_protein", "stuck", "warn", -28, -23, ["milk_analyzer_02"], "Соотношение жир/белок не меняется — повтор анализатора"),
        # Health tab
        ("mastitis", "range", "warn", -42, -38, [], "Высокая частота мастита: 4 случая за неделю"),
        ("mastitis", "gap", "warn", -20, -19, [], "Пропуск регистрации маститов в гр. 2"),
        ("health_issues", "range", "high", -35, -28, [], "Резкий рост клинических случаев — 3× от baseline"),
        # Reproduction tab
        ("inseminations", "gap", "warn", -25, -22, [], "Пропуск регистрации осеменений (АИ-техник offline)"),
        ("repro_rates", "flatline", "warn", -50, -44, [], "CR застрял на 32% — подозрение на неточность регистрации"),
        ("days_open", "range", "warn", -32, -28, [], "Days open поднялся выше 145д — триггер пересмотра ВВП"),
        ("vwp", "range", "warn", -38, -33, [], "ВВП ушёл выше 65д — корректировка протокола"),
        # Behavior tab
        ("rumination", "stuck", "warn", -45, -39, ["collar_grp4"], "Залипание датчиков жвачки в гр. 4"),
        ("activity", "gap", "warn", -18, -14, ["wifi_barn1"], "Пропуск активности — Wi-Fi сбой в коровнике 1"),
        # Feed tab
        ("dmi", "range", "warn", -40, -34, ["mixer_02"], "DMI падение -8% при стабильной загрузке миксера"),
        ("dmi", "flatline", "warn", -22, -19, ["scale_grp3"], "DMI плоский 4 дня — подозрение на залипание весов"),
        ("feed_cost", "gap", "warn", -12, -10, [], "Пропуск ввода цен по компонентам рациона"),
        # Weather tab
        ("thi", "range", "high", -55, -50, ["weather_station"], "THI 78+ — heat-stress alert в группе 4"),
    ]
    incidents = [
        {
            "incident_id": f"qc_seed_{metric}_{detector}_{uuid.uuid4().hex[:6]}",
            "metric_id": metric,
            "period_start": today + timedelta(days=ds),
            "period_end": today + timedelta(days=de),
            "detector_type": detector,
            "severity": severity,
            "affected_sensors": sensors,
            "root_cause": cause,
        }
        for metric, detector, severity, ds, de, sensors, cause in specs
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
