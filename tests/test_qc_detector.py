"""QC detector heuristics tests."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _seed_milkings(farm_id, animal_id, day_value_pairs):
    """day_value_pairs: list[(date_str, milk_kg, scc)]"""
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            # Seed parent rows to satisfy FKs (tenant_id == farm_id in single-tenant demo)
            cur.execute(
                """
                INSERT INTO dm_farms (tenant_id, farm_id, farm_name, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
                """,
                (farm_id, farm_id, f"qc_test_farm_{farm_id}"),
            )
            cur.execute(
                """
                INSERT INTO dm_animals (tenant_id, animal_id, farm_id, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
                """,
                (farm_id, animal_id, farm_id),
            )
            for d, m, scc in day_value_pairs:
                rec_id = f"rec_{uuid.uuid4().hex[:10]}"
                cur.execute(
                    """
                    INSERT INTO dm_milkings_daily
                      (tenant_id, record_id, animal_id, date, milk_kg, scc_cells_ml, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                    """,
                    (farm_id, rec_id, animal_id, d, m, scc),
                )
        conn.commit()


def _cleanup(farm_id):
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dm_milkings_daily WHERE tenant_id=%s", (farm_id,))
            cur.execute("DELETE FROM qc_incidents WHERE farm_id=%s", (farm_id,))
            cur.execute("DELETE FROM qc_scan_state WHERE farm_id=%s", (farm_id,))
            cur.execute("DELETE FROM dm_animals WHERE tenant_id=%s", (farm_id,))
            cur.execute("DELETE FROM dm_farms WHERE tenant_id=%s", (farm_id,))
        conn.commit()


def test_gap_detection_emits_incident():
    from web_cabinet.analytics import qc_detector
    farm_id = f"qct_{uuid.uuid4().hex[:6]}"
    _cleanup(farm_id)
    today = datetime.now(timezone.utc).date()
    pairs = [
        (today - timedelta(days=10), 25.0, 200000),
        (today - timedelta(days=9),  24.5, 210000),
        (today - timedelta(days=8),  25.2, 205000),
        # gap days 7,6,5 missing
        (today - timedelta(days=4),  24.8, 215000),
    ]
    _seed_milkings(farm_id, "A1", pairs)
    try:
        new_incidents = qc_detector.detect_qc_incidents(farm_id)
        kinds = {i.detector_type for i in new_incidents}
        assert "gap" in kinds, f"expected a gap incident, got: {kinds}"
    finally:
        _cleanup(farm_id)


def test_range_violation_emits_incident():
    from web_cabinet.analytics import qc_detector
    farm_id = f"qcr_{uuid.uuid4().hex[:6]}"
    _cleanup(farm_id)
    today = datetime.now(timezone.utc).date()
    pairs = [(today - timedelta(days=i), 250.0, 200000) for i in range(5)]
    _seed_milkings(farm_id, "A1", pairs)
    try:
        new_incidents = qc_detector.detect_qc_incidents(farm_id)
        assert any(i.detector_type == "range" for i in new_incidents)
    finally:
        _cleanup(farm_id)


def test_stuck_value_emits_incident():
    from web_cabinet.analytics import qc_detector
    farm_id = f"qcs_{uuid.uuid4().hex[:6]}"
    _cleanup(farm_id)
    today = datetime.now(timezone.utc).date()
    pairs = [(today - timedelta(days=i), 25.0, 250000) for i in range(8)]
    _seed_milkings(farm_id, "A1", pairs)
    try:
        new_incidents = qc_detector.detect_qc_incidents(farm_id)
        assert any(i.detector_type == "stuck" for i in new_incidents)
    finally:
        _cleanup(farm_id)


def test_dedup_does_not_create_twice():
    from web_cabinet.analytics import qc_detector
    farm_id = f"qcd_{uuid.uuid4().hex[:6]}"
    _cleanup(farm_id)
    today = datetime.now(timezone.utc).date()
    pairs = [(today - timedelta(days=i), 250.0, 200000) for i in range(5)]
    _seed_milkings(farm_id, "A1", pairs)
    try:
        first = qc_detector.detect_qc_incidents(farm_id)
        second = qc_detector.detect_qc_incidents(farm_id)
        assert len(first) >= 1
        assert len(second) == 0
    finally:
        _cleanup(farm_id)


def test_cron_gate_skips_when_no_new_data():
    from web_cabinet.analytics import qc_detector
    from web_cabinet.insights_v1 import _conn
    farm_id = f"qcg_{uuid.uuid4().hex[:6]}"
    _cleanup(farm_id)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO qc_scan_state (farm_id, last_scan_at) VALUES (%s, NOW()) "
                "ON CONFLICT (farm_id) DO UPDATE SET last_scan_at=NOW()",
                (farm_id,),
            )
        conn.commit()
    try:
        assert qc_detector.cron_should_skip_qc_scan(farm_id) is True
    finally:
        _cleanup(farm_id)
