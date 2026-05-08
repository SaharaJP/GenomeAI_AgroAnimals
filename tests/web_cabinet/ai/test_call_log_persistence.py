"""Tests for ai_call_log persistence helper (best-effort)."""
from unittest.mock import MagicMock

from web_cabinet.ai.call_log import persist_ai_call, _truncate


def test_truncate_preserves_short_text():
    assert _truncate("hello") == "hello"


def test_truncate_caps_at_50kb_with_marker():
    long = "x" * 60_000
    out = _truncate(long)
    assert out.startswith("[TRUNCATED:")
    assert len(out) < 51_500  # marker + 50KB body


def test_persist_inserts_row():
    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

    persist_ai_call(
        conn=fake_conn,
        endpoint="morning-brief",
        task_type="default",
        model="claude-sonnet-4-6",
        user_id="admin",
        input_tokens=100,
        output_tokens=50,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        latency_ms=850,
        error=None,
        prompt="привет",
        response="ответ",
        evidence_chips=["chip1"],
        tools_used=[{"name": "get_kpi_summary"}],
    )
    fake_cursor.execute.assert_called_once()
    fake_conn.commit.assert_called_once()


def test_persist_swallows_exceptions(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    fake_conn = MagicMock()
    fake_conn.cursor.side_effect = RuntimeError("db down")

    persist_ai_call(
        conn=fake_conn,
        endpoint="ask-farm",
        task_type="default",
        model="claude-sonnet-4-6",
        user_id=None,
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        latency_ms=0,
        error="kaboom",
        prompt=None,
        response=None,
        evidence_chips=None,
        tools_used=None,
    )
    assert any("ai_call_log persist failed" in rec.message for rec in caplog.records)
