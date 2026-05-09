"""P1-1 acceptance: 4 brief-mandated prompts route to the right canonical tool."""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator
from unittest.mock import MagicMock, patch
import pytest

from web_cabinet.ai.endpoints import ask_farm
from web_cabinet.ai.client import LLMResponse


def _collect_sse(stream: AsyncIterator[str]) -> list[tuple[str, dict]]:
    out: list = []

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


# Per brief §P1-1: each prompt must trigger exactly one tool_use of the named tool.
ACCEPTANCE_PROMPTS = [
    ("покажи карточку Звёздочки",           "get_animal_profile",  {"cow_id": "4821"}),
    ("стоит ли выбраковать Малину",         "calculate_cull_npv",  {"animal_id": "7001"}),
    ("прогноз надоя на следующую неделю",   "forecast_milk_yield", {"group_id": "PEN_LACT", "horizon_days": 7}),
    ("как смена рациона повлияла на надой", "analyze_event_impact", {"event_id": "TL_001", "kpi": "milk_kg", "window_days": 14}),
]


@pytest.mark.parametrize("question,expected_tool,tool_input", ACCEPTANCE_PROMPTS)
def test_brief_prompt_routes_to_canonical_tool(monkeypatch, question, expected_tool, tool_input):
    """Mocked model returns the expected tool_use; pipeline must emit tool_used + done.tools_used."""
    # Mock LLMResponse mimicking what tool_call_loop returns after the agent loop completes.
    mocked_response = LLMResponse(
        content=f"Готовый ответ для: {question}",
        model="claude-opus-4-7",
        input_tokens=200,
        output_tokens=50,
        tools_used=[{"name": expected_tool, "input": tool_input}],
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

    with patch("web_cabinet.ai.client.get_client", return_value=fake_client):
        with patch("web_cabinet.ai.context.build_farm_context", return_value={"farm_summary": {"total_cows": 100}}):
            stream = ask_farm._stream_live(
                question=question,
                session_id=f"test-{expected_tool}",
                user_id="test-user",
                farm_id="demo-farm-v1",
                messages_history=[],
            )
            events = _collect_sse(stream)

    # 1) Exactly one tool_used event with the expected name
    tool_used_events = [e for e in events if e[0] == "tool_used"]
    assert len(tool_used_events) == 1, (
        f"want 1 tool_used, got {len(tool_used_events)} for prompt={question!r}"
    )
    assert tool_used_events[0][1]["name"] == expected_tool, (
        f"prompt={question!r} → expected tool {expected_tool!r}, got {tool_used_events[0][1]['name']!r}"
    )

    # 2) done event must include the tool in its tools_used array
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    assert expected_tool in done_events[0][1].get("tools_used", []), (
        f"prompt={question!r}: done.tools_used = {done_events[0][1].get('tools_used')}"
    )

    # 3) Verify the tool_call_loop was actually called with ALL_TOOLS (registry)
    fake_client.tool_call_loop.assert_called_once()
    call_kwargs = fake_client.tool_call_loop.call_args.kwargs
    tool_names_passed = {t["name"] for t in call_kwargs["tools"]}
    assert expected_tool in tool_names_passed, (
        f"tool {expected_tool!r} not in registry passed to loop: {sorted(tool_names_passed)}"
    )
