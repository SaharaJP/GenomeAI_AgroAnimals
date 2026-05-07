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
    try:
        import psycopg2 as _pg  # type: ignore
    except ImportError:  # pragma: no cover - psycopg v3 fallback
        import psycopg as _pg  # type: ignore
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    iid = f"ins_test_{uuid.uuid4().hex[:8]}"
    conn = _pg.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scanner_insights
          (insight_id, farm_id, title, category, priority, status,
           generated_at_utc, generator, payload_json,
           severity, body, action, animal_ids, recommendations)
        VALUES (%s,%s,%s,%s,%s,%s, NOW()::text,'seed_test', %s,
                'warn','Body','Action', %s::jsonb, %s::jsonb)
        """,
        (iid, farm_id, 'Test title', 'health', 'medium', 'to_check',
         json.dumps({}), json.dumps([]), json.dumps([])),
    )
    conn.commit()
    cur.close()
    conn.close()
    yield iid
    conn = _pg.connect(dsn)
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
