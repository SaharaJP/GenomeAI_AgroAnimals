"""Scanner respects insight_settings.enabled_categories."""
from __future__ import annotations

import os
import json
import uuid
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _put_cron_settings(farm_id: str, categories: list[str]) -> None:
    """Direct insert of cron-user settings for a farm."""
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insight_settings (user_id, farm_id, min_severity, enabled_categories, updated_at)
                VALUES ('cron', %s, 'info', %s::jsonb, NOW())
                ON CONFLICT (user_id, farm_id) DO UPDATE
                  SET enabled_categories = EXCLUDED.enabled_categories,
                      updated_at = NOW()
                """,
                (farm_id, json.dumps(categories)),
            )
        conn.commit()


def _delete_cron_settings(farm_id: str) -> None:
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM insight_settings WHERE user_id='cron' AND farm_id=%s",
                (farm_id,),
            )
        conn.commit()


def test_scanner_filters_disabled_categories(tmp_path, monkeypatch):
    """When a farm has only 'health' enabled, scanner drops production insights."""
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = f"TEST_FILTER_FARM_{uuid.uuid4().hex[:6]}"
    _put_cron_settings(farm_id, ["health"])
    try:
        fake_seeded = [
            {
                "insight_id": f"ins_h_{uuid.uuid4().hex[:6]}",
                "title": "Mastitis", "description": "x",
                "category": "health", "priority": "high",
                "evidence_ids": ["e1"], "affected_cow_ids": ["a1"],
                "recommendations": [],
            },
            {
                "insight_id": f"ins_p_{uuid.uuid4().hex[:6]}",
                "title": "Yield", "description": "y",
                "category": "production", "priority": "high",
                "evidence_ids": ["e2"], "affected_cow_ids": ["a2"],
                "recommendations": [],
            },
        ]
        seed_file = tmp_path / "scan_now_seeded.json"
        seed_file.write_text(json.dumps(fake_seeded), encoding="utf-8")
        monkeypatch.setattr(scn, "_SCAN_NOW_SEEDED_PATH", seed_file)

        # Mock get_ai_settings to enable demo mode
        with patch.object(scn, "get_ai_settings") as gs:
            class FakeSettings:
                GENOMEAI_AI_DEMO_MODE = True
                GENOMEAI_DEMO_FARM_ID = farm_id
            gs.return_value = FakeSettings()
            result = scn.scan_for_new_insights(farm_id)
        cats = {i.category for i in result}
        assert cats == {"health"}, f"expected only health, got {cats}"
    finally:
        _delete_cron_settings(farm_id)


def test_scanner_no_settings_returns_all_categories(tmp_path, monkeypatch):
    """Backward compat: farm with NO settings row gets all categories."""
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = f"TEST_NOSETTINGS_FARM_{uuid.uuid4().hex[:6]}"
    # Ensure no settings row
    _delete_cron_settings(farm_id)
    fake_seeded = [
        {
            "insight_id": f"ins_h_{uuid.uuid4().hex[:6]}",
            "title": "X", "description": "x",
            "category": "health", "priority": "high",
            "evidence_ids": ["e1"], "affected_cow_ids": ["a1"],
            "recommendations": [],
        },
        {
            "insight_id": f"ins_p_{uuid.uuid4().hex[:6]}",
            "title": "Y", "description": "y",
            "category": "production", "priority": "high",
            "evidence_ids": ["e2"], "affected_cow_ids": ["a2"],
            "recommendations": [],
        },
    ]
    seed_file = tmp_path / "scan_now_seeded.json"
    seed_file.write_text(json.dumps(fake_seeded), encoding="utf-8")
    monkeypatch.setattr(scn, "_SCAN_NOW_SEEDED_PATH", seed_file)
    with patch.object(scn, "get_ai_settings") as gs:
        class FakeSettings:
            GENOMEAI_AI_DEMO_MODE = True
            GENOMEAI_DEMO_FARM_ID = farm_id
        gs.return_value = FakeSettings()
        result = scn.scan_for_new_insights(farm_id)
    cats = {i.category for i in result}
    assert cats == {"health", "production"}, f"expected both, got {cats}"


def test_dedup_skips_soft_deleted():
    """Scanner's get_active_insights surfaces soft-deleted rows so dedup won't resurrect them."""
    import json
    import uuid as _uuid
    from web_cabinet.ai.background import insight_scanner as scn
    from web_cabinet.insights_v1 import _conn

    farm_id = f"TEST_DEDUP_FARM_{_uuid.uuid4().hex[:6]}"
    iid = f"ins_dedup_{_uuid.uuid4().hex[:8]}"
    payload = {"evidence_ids": ["E_X"]}
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scanner_insights
                       (insight_id, farm_id, title, category, priority, status,
                        generated_at_utc, generator, payload_json, deleted_at)
                       VALUES (%s,%s,'Existing','health','high','to_check',
                               NOW()::text,'test', %s, NOW())
                       ON CONFLICT (insight_id) DO NOTHING""",
                    (iid, farm_id, json.dumps(payload)),
                )
            conn.commit()

        rows = scn.get_active_insights(farm_id)
        ev_sets = [set(r.get("evidence_ids", [])) for r in rows]
        assert {"E_X"} in ev_sets, (
            f"deleted row must be visible to dedup, got evidence sets: {ev_sets}"
        )
    finally:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM scanner_insights WHERE insight_id=%s", (iid,))
            conn.commit()
