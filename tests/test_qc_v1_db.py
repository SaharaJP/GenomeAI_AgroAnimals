"""qc_v1 boundary CRUD tests."""
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
def farm_id():
    return f"qc_test_{uuid.uuid4().hex[:6]}"


@pytest.fixture
def seeded_incident(farm_id):
    from web_cabinet.insights_v1 import _conn
    iid = f"qc_{uuid.uuid4().hex[:8]}"
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO qc_incidents
                  (incident_id, farm_id, metric_id, period_start, period_end,
                   detector_type, severity, affected_sensors, ai_description, root_cause)
                VALUES (%s, %s, 'milk_ecm', NOW() - INTERVAL '3 days', NOW() - INTERVAL '1 day',
                        'gap', 'warn', %s::jsonb, 'Sensor gap', 'gap_milk_meter')
                """,
                (iid, farm_id, json.dumps(['milk_meter_1'])),
            )
        conn.commit()
    yield iid
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM qc_incidents WHERE farm_id=%s", (farm_id,))
        conn.commit()


def test_list_returns_seeded(seeded_incident, farm_id):
    from web_cabinet import qc_v1
    resp = qc_v1.list_incidents(farm_id=farm_id, active=True)
    assert resp.total == 1
    assert resp.items[0].incident_id == seeded_incident
    assert resp.items[0].metric_id == 'milk_ecm'
    assert resp.items[0].root_cause == 'gap_milk_meter'


def test_list_filters_by_metric(seeded_incident, farm_id):
    from web_cabinet import qc_v1
    assert qc_v1.list_incidents(farm_id=farm_id, metric_id='milk_ecm').total == 1
    assert qc_v1.list_incidents(farm_id=farm_id, metric_id='scc').total == 0


def test_get_returns_incident(seeded_incident):
    from web_cabinet import qc_v1
    item = qc_v1.get_incident(seeded_incident)
    assert item is not None
    assert item.incident_id == seeded_incident


def test_dismiss_marks_status(seeded_incident, farm_id):
    from web_cabinet import qc_v1
    assert qc_v1.dismiss_incident(seeded_incident) is True
    assert qc_v1.list_incidents(farm_id=farm_id, active=True).total == 0
    item = qc_v1.get_incident(seeded_incident)
    assert item is not None
    assert item.status == 'dismissed'


def test_dismiss_idempotent(seeded_incident):
    from web_cabinet import qc_v1
    assert qc_v1.dismiss_incident(seeded_incident) is True
    assert qc_v1.dismiss_incident(seeded_incident) is True
