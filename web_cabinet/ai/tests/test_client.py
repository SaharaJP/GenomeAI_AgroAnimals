"""Unit тесты для AnthropicClient: mock Anthropic, retry, caching."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from web_cabinet.ai.client import AnthropicClient, LLMResponse, _is_transient


class TestLLMResponse:
    def test_cache_hit_when_cache_read_tokens_positive(self):
        r = LLMResponse("text", "claude-sonnet-4-6", 100, 50, cache_read_tokens=80)
        assert r.cache_hit is True

    def test_cache_miss_when_no_cache_read_tokens(self):
        r = LLMResponse("text", "claude-sonnet-4-6", 100, 50, cache_read_tokens=0)
        assert r.cache_hit is False

    def test_total_tokens(self):
        r = LLMResponse("text", "claude-sonnet-4-6", 100, 50)
        assert r.total_tokens == 150


class TestIsTransient:
    def test_timeout_is_transient(self):
        exc = TimeoutError("connection timeout")
        assert _is_transient(exc) is True

    def test_rate_limit_is_transient(self):
        exc = Exception("rate limit exceeded")
        assert _is_transient(exc) is True

    def test_value_error_not_transient(self):
        exc = ValueError("invalid input")
        assert _is_transient(exc) is False


class TestModelRouting:
    def test_opus_for_morning_brief(self):
        client = AnthropicClient(api_key="test-key")
        model = client._model_for_task("morning_brief")
        settings = client._settings
        assert model == settings.GENOMEAI_AI_OPUS_MODEL

    def test_sonnet_for_default(self):
        client = AnthropicClient(api_key="test-key")
        model = client._model_for_task("ask_farm")
        settings = client._settings
        assert model == settings.GENOMEAI_AI_DEFAULT_MODEL


class TestSystemBlocks:
    def test_with_farm_context_adds_cache_control_to_context(self):
        client = AnthropicClient(api_key="test-key")
        blocks = client._build_system_blocks("System prompt.", farm_context="Farm data here")
        assert len(blocks) == 2
        assert "cache_control" not in blocks[0]
        assert blocks[1]["cache_control"] == {"type": "ephemeral"}
        assert "farm_context" in blocks[1]["text"]

    def test_without_farm_context_cache_control_on_system(self):
        client = AnthropicClient(api_key="test-key")
        blocks = client._build_system_blocks("System prompt.")
        assert len(blocks) == 1
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}


class TestGenerateWithMock:
    def _make_mock_response(self, text: str = "Ответ на русском") -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=text)]
        mock_resp.model = "claude-sonnet-4-6"
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 50
        mock_resp.usage.cache_creation_input_tokens = 80
        mock_resp.usage.cache_read_input_tokens = 0
        return mock_resp

    def test_generate_returns_llm_response(self):
        client = AnthropicClient(api_key="test-key")
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = self._make_mock_response()
        client._client = mock_anthropic

        result = client.generate("Тест вопрос", system_prompt="Системный промпт")
        assert isinstance(result, LLMResponse)
        assert result.content == "Ответ на русском"
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_generate_retries_on_retryable_error(self):
        client = AnthropicClient(api_key="test-key")
        mock_anthropic = MagicMock()

        call_count = 0
        mock_ok = self._make_mock_response("OK после retry")

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                exc = Exception("rate limit")
                raise exc
            return mock_ok

        mock_anthropic.messages.create.side_effect = side_effect
        client._client = mock_anthropic

        with patch("time.sleep"):
            result = client.generate("Тест")

        assert call_count == 2
        assert result.content == "OK после retry"

    def test_generate_raises_on_non_retryable_error(self):
        client = AnthropicClient(api_key="test-key")
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = ValueError("bad request")
        client._client = mock_anthropic

        with pytest.raises(ValueError):
            client.generate("Тест")

    def test_generate_logs_call(self, caplog):
        import logging
        client = AnthropicClient(api_key="test-key")
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = self._make_mock_response()
        client._client = mock_anthropic

        with caplog.at_level(logging.INFO, logger="genomeai.ai.client"):
            client.generate("Тест", task_type="ask_farm", user_id="user123")

        assert any("llm_call" in r.message for r in caplog.records)
        log_record = next(r for r in caplog.records if "llm_call" in r.message)
        log_data = json.loads(log_record.message)
        assert log_data["task_type"] == "ask_farm"
        assert log_data["user_id"] == "user123"
