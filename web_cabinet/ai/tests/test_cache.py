"""Тесты Redis-кэша: unit (mocked) + ключи, TTL, graceful degradation."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from web_cabinet.ai.cache import AICache


class TestAICacheKeys:
    def test_key_is_deterministic(self):
        key1 = AICache.make_key("morning_brief", {"date": "2026-04-21", "farm": "demo"})
        key2 = AICache.make_key("morning_brief", {"farm": "demo", "date": "2026-04-21"})
        assert key1 == key2

    def test_key_differs_by_endpoint(self):
        k1 = AICache.make_key("morning_brief", {"date": "2026-04-21"})
        k2 = AICache.make_key("weekly_brief", {"date": "2026-04-21"})
        assert k1 != k2

    def test_key_differs_by_params(self):
        k1 = AICache.make_key("ask_farm", {"question": "Вопрос А"})
        k2 = AICache.make_key("ask_farm", {"question": "Вопрос Б"})
        assert k1 != k2

    def test_key_has_prefix(self):
        key = AICache.make_key("health", {})
        assert key.startswith("genomeai:ai:")


class TestAICacheDisabled:
    def test_get_returns_none_when_disabled(self):
        cache = AICache("redis://localhost:6379/0", enabled=False)
        result = cache.get("any-key")
        assert result is None

    def test_set_does_nothing_when_disabled(self):
        cache = AICache("redis://localhost:6379/0", enabled=False)
        cache.set("any-key", "value")

    def test_get_json_returns_none_when_disabled(self):
        cache = AICache("redis://localhost:6379/0", enabled=False)
        result = cache.get_json("endpoint", {"k": "v"})
        assert result is None


class TestAICacheWithMockRedis:
    def _make_cache(self) -> tuple[AICache, MagicMock]:
        cache = AICache("redis://localhost:6379/0", ttl_seconds=300, enabled=True)
        mock_redis = MagicMock()
        cache._client = mock_redis
        return cache, mock_redis

    def test_get_hit(self):
        cache, mock_redis = self._make_cache()
        mock_redis.get.return_value = '{"answer": "Тест"}'
        result = cache.get("test-key")
        assert result == '{"answer": "Тест"}'
        mock_redis.get.assert_called_once_with("test-key")

    def test_get_miss(self):
        cache, mock_redis = self._make_cache()
        mock_redis.get.return_value = None
        result = cache.get("test-key")
        assert result is None

    def test_set_uses_setex_with_ttl(self):
        cache, mock_redis = self._make_cache()
        cache.set("test-key", "value", ttl=60)
        mock_redis.setex.assert_called_once_with("test-key", 60, "value")

    def test_set_uses_default_ttl(self):
        cache, mock_redis = self._make_cache()
        cache.set("test-key", "value")
        mock_redis.setex.assert_called_once_with("test-key", 300, "value")

    def test_get_json_deserializes(self):
        cache, mock_redis = self._make_cache()
        data = {"answer": "Молочная ферма", "tokens": 100}
        mock_redis.get.return_value = json.dumps(data, ensure_ascii=False)
        result = cache.get_json("ask_farm", {"q": "test"})
        assert result == data

    def test_set_json_serializes(self):
        cache, mock_redis = self._make_cache()
        data = {"answer": "Тест"}
        cache.set_json("ask_farm", {"q": "test"}, data)
        call_args = mock_redis.setex.call_args
        stored = json.loads(call_args[0][2])
        assert stored == data

    def test_invalidate_calls_delete(self):
        cache, mock_redis = self._make_cache()
        cache.invalidate("test-key")
        mock_redis.delete.assert_called_once_with("test-key")

    def test_graceful_degradation_on_redis_error(self):
        cache, mock_redis = self._make_cache()
        mock_redis.get.side_effect = ConnectionError("Redis недоступен")
        result = cache.get("test-key")
        assert result is None

    def test_set_graceful_degradation_on_redis_error(self):
        cache, mock_redis = self._make_cache()
        mock_redis.setex.side_effect = ConnectionError("Redis недоступен")
        cache.set("test-key", "value")

    def test_ping_returns_true_on_success(self):
        cache, mock_redis = self._make_cache()
        mock_redis.ping.return_value = True
        assert cache.ping() is True

    def test_ping_returns_false_on_error(self):
        cache, mock_redis = self._make_cache()
        mock_redis.ping.side_effect = ConnectionError("down")
        assert cache.ping() is False
