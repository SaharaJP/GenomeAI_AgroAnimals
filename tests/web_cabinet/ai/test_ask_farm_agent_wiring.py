"""Test that ask_farm._stream_live runs tool_call_loop and emits tool_used events."""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator
from unittest.mock import MagicMock, patch
import pytest

from web_cabinet.ai.endpoints import ask_farm
from web_cabinet.ai.client import LLMResponse


def _collect_sse(stream: AsyncIterator[str]) -> list[tuple[str, dict]]:
    """Drain an async SSE generator into a list of (event_name, data_dict)."""
    out: list[list] = []

    async def _drain():
        async for chunk in stream:
            for raw in chunk.strip().split("\n"):
                raw = raw.strip()
                if raw.startswith("event: "):
                    out.append([raw[len("event: "):], None])
                elif raw.startswith("data: ") and out:
                    out[-1][1] = json.loads(raw[len("data: "):])
        return out

    asyncio.run(_drain())
    return out


def test_stream_live_emits_tool_used_then_tokens(monkeypatch):
    """Mock tool_call_loop so it returns a known LLMResponse with one tool_used."""
    mocked_response = LLMResponse(
        content="Звёздочка: SCC 180 тыс., надой 28 кг.",
        model="claude-opus-4-7",
        input_tokens=200,
        output_tokens=50,
        tools_used=[{"name": "get_animal_profile", "input": {"cow_id": "4821"}}],
    )

    fake_client = MagicMock()
    fake_client.tool_call_loop = MagicMock(return_value=mocked_response)

    monkeypatch.setattr(
        ask_farm,
        "get_ai_settings",
        lambda: MagicMock(
            GENOMEAI_AI_DEFAULT_MODEL="claude-opus-4-7",
            is_configured=True,
            GENOMEAI_AI_DEMO_MODE=False,
            GENOMEAI_AI_RATE_LIMIT_PER_MIN=60,
            GENOMEAI_AI_RATE_LIMIT_PER_HOUR=600,
        ),
    )

    # Patch the deferred imports inside _stream_live
    with patch("web_cabinet.ai.client.get_client", return_value=fake_client):
        with patch(
            "web_cabinet.ai.context.build_farm_context",
            return_value={"farm_summary": {"total_cows": 100}},
        ):
            stream = ask_farm._stream_live(
                question="карточку Звёздочки",
                session_id="test-session",
                user_id="test-user",
                farm_id="demo-farm-v1",
                messages_history=[],
            )
            events = _collect_sse(stream)

    event_names = [e[0] for e in events]
    assert "start" in event_names
    assert "tool_used" in event_names, f"got events: {event_names}"
    assert "token" in event_names
    assert "done" in event_names

    tool_used_events = [e for e in events if e[0] == "tool_used"]
    assert len(tool_used_events) == 1
    assert tool_used_events[0][1]["name"] == "get_animal_profile"

    # tool_used events must appear before first token event
    tool_used_idx = event_names.index("tool_used")
    first_token_idx = event_names.index("token")
    assert tool_used_idx < first_token_idx, (
        f"tool_used at {tool_used_idx} should precede first token at {first_token_idx}"
    )

    done_event = next(e for e in events if e[0] == "done")
    assert done_event[1]["tools_used"] == ["get_animal_profile"]
    assert "total_tokens" in done_event[1]
    assert done_event[1]["total_tokens"]["input"] == 200
    assert done_event[1]["total_tokens"]["output"] == 50


def test_stream_live_handles_loop_exception(monkeypatch):
    """If tool_call_loop raises, an SSE error event is emitted."""
    fake_client = MagicMock()
    fake_client.tool_call_loop = MagicMock(side_effect=RuntimeError("simulated"))

    monkeypatch.setattr(
        ask_farm,
        "get_ai_settings",
        lambda: MagicMock(
            GENOMEAI_AI_DEFAULT_MODEL="claude-opus-4-7",
            is_configured=True,
            GENOMEAI_AI_DEMO_MODE=False,
            GENOMEAI_AI_RATE_LIMIT_PER_MIN=60,
            GENOMEAI_AI_RATE_LIMIT_PER_HOUR=600,
        ),
    )

    with patch("web_cabinet.ai.client.get_client", return_value=fake_client):
        with patch("web_cabinet.ai.context.build_farm_context", return_value={}):
            stream = ask_farm._stream_live(
                question="boom",
                session_id="s",
                user_id="u",
                farm_id="demo-farm-v1",
                messages_history=[],
            )
            events = _collect_sse(stream)

    event_names = [e[0] for e in events]
    assert "error" in event_names, f"got {event_names}"
    # After error there should be no token or done events
    assert "token" not in event_names
    assert "done" not in event_names
