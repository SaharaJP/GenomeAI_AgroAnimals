"""Cron path skips Claude when no new inputs arrived since last scan."""
from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")),
    reason="needs Postgres DSN",
)


def _set_last_scan(farm_id: str, when) -> None:
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insight_scan_state (farm_id, last_scan_at)
                VALUES (%s, %s)
                ON CONFLICT (farm_id) DO UPDATE SET last_scan_at = EXCLUDED.last_scan_at
                """,
                (farm_id, when),
            )
        conn.commit()


def _clear_state(farm_id: str) -> None:
    from web_cabinet.insights_v1 import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM insight_scan_state WHERE farm_id=%s", (farm_id,))
            cur.execute(
                "DELETE FROM timeline_events WHERE timeline_event_id LIKE %s",
                (f"ev_gate_{farm_id}_%",),
            )
        conn.commit()


def test_cron_skips_when_no_new_inputs():
    """No new timeline events / alerts since last_scan_at -> skip."""
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = f"TEST_GATE_NONE_{uuid.uuid4().hex[:6]}"
    _clear_state(farm_id)
    try:
        _set_last_scan(farm_id, datetime.now(timezone.utc))
        with patch.object(scn, "scan_for_new_insights") as mock_scan:
            assert scn.cron_should_skip_scan(farm_id) is True
            mock_scan.assert_not_called()
    finally:
        _clear_state(farm_id)


def test_cron_runs_when_new_event_present():
    """An event added after last_scan_at means there IS new input -> do not skip."""
    from web_cabinet.ai.background import insight_scanner as scn
    from web_cabinet.insights_v1 import _conn
    farm_id = f"TEST_GATE_EVENT_{uuid.uuid4().hex[:6]}"
    _clear_state(farm_id)
    try:
        # Set last scan two hours ago, then insert a fresh event for this tenant
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        _set_last_scan(farm_id, past)
        ev_id = f"ev_gate_{farm_id}_1"
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO timeline_events
                      (timeline_event_id, tenant_id, event_type, title, event_date, created_at)
                    VALUES (%s, %s, 'test', 'gate_test', NOW()::text, NOW()::text)
                    ON CONFLICT (timeline_event_id) DO NOTHING
                    """,
                    (ev_id, farm_id),
                )
            conn.commit()
        assert scn.cron_should_skip_scan(farm_id) is False
    finally:
        _clear_state(farm_id)


def test_cron_runs_when_state_missing():
    """Never-scanned farm (no state row) -> always run."""
    from web_cabinet.ai.background import insight_scanner as scn
    farm_id = f"TEST_GATE_NEW_{uuid.uuid4().hex[:6]}"
    _clear_state(farm_id)
    assert scn.cron_should_skip_scan(farm_id) is False


def test_manual_scan_now_bypasses_gate():
    """scan_for_new_insights does not consult the cron gate."""
    import inspect
    from web_cabinet.ai.background import insight_scanner as scn
    src = inspect.getsource(scn.scan_for_new_insights)
    assert "cron_should_skip_scan" not in src, (
        "scan_for_new_insights must NOT call cron_should_skip_scan"
    )
