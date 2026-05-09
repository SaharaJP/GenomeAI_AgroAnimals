"""Test bounded agent loop AnthropicClient.tool_call_loop."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from web_cabinet.ai.client import AnthropicClient


class _StubBlock:
    """Mock for an Anthropic content block (text or tool_use)."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.type = kw.get("type", "text")


def _make_response(*, stop_reason: str, blocks: list, model: str = "claude-opus-4-7"):
    r = MagicMock()
    r.model = model
    r.content = blocks
    r.stop_reason = stop_reason
    r.usage.input_tokens = 100
    r.usage.output_tokens = 50
    r.usage.cache_creation_input_tokens = 0
    r.usage.cache_read_input_tokens = 0
    return r


def test_tool_call_loop_no_tools_used(monkeypatch):
    """Model returns end_turn directly without any tool_use → loop exits with text."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    fake.messages.create.return_value = _make_response(
        stop_reason="end_turn",
        blocks=[_StubBlock(type="text", text="Привет")],
    )
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    executor_calls = []
    result = client.tool_call_loop(
        user_message="Привет",
        tools=[],
        executor=lambda name, inp: executor_calls.append((name, inp)) or {},
    )
    assert result.content == "Привет"
    assert result.tools_used == []
    assert executor_calls == []


def test_tool_call_loop_one_tool_then_stop(monkeypatch):
    """Model uses one tool, gets result, returns final text."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    first = _make_response(
        stop_reason="tool_use",
        blocks=[_StubBlock(
            type="tool_use",
            id="tool_1",
            name="get_animal_profile",
            input={"cow_id": "Star"},
        )],
    )
    second = _make_response(
        stop_reason="end_turn",
        blocks=[_StubBlock(type="text", text="SCC 180 тыс., надой 28 кг.")],
    )
    fake.messages.create.side_effect = [first, second]
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    captured = []
    def executor(name, inp):
        captured.append((name, inp))
        return {"scc": 180000, "milk_kg": 28}

    result = client.tool_call_loop(
        user_message="карточку Звёздочки",
        tools=[{"name": "get_animal_profile", "input_schema": {"type": "object", "properties": {}}}],
        executor=executor,
    )
    assert result.content == "SCC 180 тыс., надой 28 кг."
    assert len(result.tools_used) == 1
    assert result.tools_used[0]["name"] == "get_animal_profile"
    assert result.tools_used[0]["input"] == {"cow_id": "Star"}
    assert captured == [("get_animal_profile", {"cow_id": "Star"})]


def test_tool_call_loop_max_iterations(monkeypatch):
    """Loop bounds iterations to prevent runaway."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    # Always return tool_use → infinite loop without bound
    fake.messages.create.return_value = _make_response(
        stop_reason="tool_use",
        blocks=[_StubBlock(type="tool_use", id="t", name="x", input={})],
    )
    monkeypatch.setattr(client, "_get_client", lambda: fake)
    with pytest.raises(RuntimeError, match="max_iterations"):
        client.tool_call_loop(
            user_message="loop",
            tools=[{"name": "x", "input_schema": {"type": "object"}}],
            executor=lambda n, i: {},
            max_iterations=2,
        )


def test_tool_call_loop_executor_exception_becomes_tool_result(monkeypatch):
    """If executor raises, the loop catches it and feeds an error to the model."""
    client = AnthropicClient(api_key="test-key")
    fake = MagicMock()
    first = _make_response(
        stop_reason="tool_use",
        blocks=[_StubBlock(type="tool_use", id="t", name="bad_tool", input={})],
    )
    second = _make_response(
        stop_reason="end_turn",
        blocks=[_StubBlock(type="text", text="Ошибка обработана.")],
    )
    fake.messages.create.side_effect = [first, second]
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    def executor(name, inp):
        raise ValueError("simulated failure")

    result = client.tool_call_loop(
        user_message="trigger",
        tools=[{"name": "bad_tool", "input_schema": {"type": "object"}}],
        executor=executor,
    )
    assert result.content == "Ошибка обработана."
    # The exception should not propagate; the loop completes
    assert len(result.tools_used) == 1
    assert result.tools_used[0]["name"] == "bad_tool"
