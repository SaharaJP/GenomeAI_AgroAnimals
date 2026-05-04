"""TDD: AnalyticsCache + @cached decorator for analytics bridges.

Tests:
- test_cache_hit_returns_same_object
- test_cache_invalidation_on_event
- test_cache_ttl
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from web_cabinet.analytics.cache import AnalyticsCache, cached

_FARM = "farm_001"
_AS_OF = date(2026, 1, 5)


# ---------------------------------------------------------------------------
# Minimal in-memory Redis simulation (no external dependency)
# ---------------------------------------------------------------------------

class _FakeRedis:
    """Stateful in-memory mock simulating the Redis operations used by AnalyticsCache."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._sets: dict[str, set] = {}
        self.published: list[tuple[str, str]] = []

    def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: Any) -> None:
        self._store[key] = value

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            count += int(k in self._store)
            self._store.pop(k, None)
            self._sets.pop(k, None)
        return count

    def sadd(self, key: str, *values: Any) -> int:
        self._sets.setdefault(key, set()).update(str(v) for v in values)
        return len(values)

    def smembers(self, key: str) -> set:
        return self._sets.get(key, set())

    def expire(self, key: str, ttl: int) -> int:
        return 1

    def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    def ping(self) -> bool:
        return True


def _make_cache() -> tuple[AnalyticsCache, _FakeRedis]:
    cache = AnalyticsCache("redis://localhost:6379/0", enabled=True)
    fake = _FakeRedis()
    cache._client = fake
    return cache, fake


# ---------------------------------------------------------------------------
# test_cache_hit_returns_same_object
# ---------------------------------------------------------------------------

class TestCacheHitReturnsSameObject:
    def test_second_call_uses_cached_value(self) -> None:
        """Second call with identical args must not invoke the underlying function."""
        cache, _ = _make_cache()
        call_count = {"n": 0}

        @cached(ttl=300, cache_instance=cache)
        def slow_fn(farm_id: str, as_of: date) -> dict:
            call_count["n"] += 1
            return {"farm_id": farm_id, "value": 42.0}

        result1 = slow_fn(_FARM, _AS_OF)
        result2 = slow_fn(_FARM, _AS_OF)

        assert call_count["n"] == 1, (
            f"Expected 1 compute, got {call_count['n']} — second call should be a cache hit"
        )
        assert result1 == result2

    def test_different_args_each_computes(self) -> None:
        """Different farm_ids must produce independent cache entries."""
        cache, _ = _make_cache()
        call_count = {"n": 0}

        @cached(ttl=300, cache_instance=cache)
        def slow_fn(farm_id: str, as_of: date) -> dict:
            call_count["n"] += 1
            return {"farm_id": farm_id}

        slow_fn("farm_A", _AS_OF)
        slow_fn("farm_B", _AS_OF)

        assert call_count["n"] == 2, "Two different farm_ids must each compute independently"

    def test_cache_key_is_deterministic(self) -> None:
        """make_key() returns identical keys for same params regardless of dict order."""
        cache, _ = _make_cache()
        k1 = cache.make_key("kpi", {"farm_id": _FARM, "as_of": str(_AS_OF)})
        k2 = cache.make_key("kpi", {"as_of": str(_AS_OF), "farm_id": _FARM})
        assert k1 == k2

    def test_cache_key_has_prefix(self) -> None:
        cache, _ = _make_cache()
        key = cache.make_key("kpi", {"farm_id": _FARM})
        assert key.startswith("genomeai:analytics:")

    def test_different_namespaces_get_different_keys(self) -> None:
        cache, _ = _make_cache()
        k1 = cache.make_key("kpi", {"farm_id": _FARM})
        k2 = cache.make_key("alerts", {"farm_id": _FARM})
        assert k1 != k2

    def test_cached_list_result_survives_round_trip(self) -> None:
        """Cached list result must equal the original after serialize/deserialize."""
        cache, _ = _make_cache()

        @cached(ttl=300, cache_instance=cache)
        def compute(farm_id: str) -> list[dict]:
            return [{"a": 1}, {"b": 2}]

        first = compute(_FARM)
        second = compute(_FARM)
        assert first == second == [{"a": 1}, {"b": 2}]


# ---------------------------------------------------------------------------
# test_cache_invalidation_on_event
# ---------------------------------------------------------------------------

class TestCacheInvalidationOnEvent:
    def test_invalidate_farm_clears_farm_index(self) -> None:
        """After invalidate_farm(), the farm index set must be empty."""
        cache, fake = _make_cache()

        @cached(ttl=300, cache_instance=cache)
        def compute(farm_id: str) -> int:
            return 99

        compute(_FARM)

        idx_key = f"genomeai:analytics:farm:{_FARM}"
        assert len(fake.smembers(idx_key)) > 0, "Farm index should be populated after first call"

        cache.invalidate_farm(_FARM)

        assert len(fake.smembers(idx_key)) == 0, "Farm index should be empty after invalidation"

    def test_recomputes_after_invalidation(self) -> None:
        """After invalidate_farm(), the next call must recompute, not return stale cache."""
        cache, _ = _make_cache()
        call_count = {"n": 0}

        @cached(ttl=300, cache_instance=cache)
        def compute(farm_id: str) -> int:
            call_count["n"] += 1
            return call_count["n"]

        compute(_FARM)
        assert call_count["n"] == 1

        cache.invalidate_farm(_FARM)

        compute(_FARM)
        assert call_count["n"] == 2, "Expected recompute after invalidation"

    def test_publish_invalidation_sends_to_correct_channel(self) -> None:
        """publish_invalidation() must publish to INVALIDATION_CHANNEL with farm_id."""
        cache, fake = _make_cache()

        cache.publish_invalidation(_FARM)

        assert len(fake.published) == 1
        channel, raw_msg = fake.published[0]
        assert channel == AnalyticsCache.INVALIDATION_CHANNEL
        msg = json.loads(raw_msg)
        assert msg["farm_id"] == _FARM

    def test_invalidate_farm_no_entries_is_safe(self) -> None:
        """invalidate_farm() must not raise when farm has no cached entries."""
        cache, _ = _make_cache()
        cache.invalidate_farm("nonexistent_farm")  # must not raise

    def test_other_farm_cache_unaffected_by_invalidation(self) -> None:
        """Invalidating farm_A must leave farm_B cache intact."""
        cache, _ = _make_cache()
        call_count = {"n": 0}

        @cached(ttl=300, cache_instance=cache)
        def compute(farm_id: str) -> int:
            call_count["n"] += 1
            return call_count["n"]

        compute("farm_A")
        compute("farm_B")
        assert call_count["n"] == 2

        cache.invalidate_farm("farm_A")

        compute("farm_B")
        assert call_count["n"] == 2, "farm_B result must still be cached after farm_A invalidation"


# ---------------------------------------------------------------------------
# test_cache_ttl
# ---------------------------------------------------------------------------

class TestCacheTTL:
    def test_cached_stores_with_given_ttl(self) -> None:
        """@cached(ttl=600) must call Redis setex with ttl=600."""
        cache = AnalyticsCache("redis://localhost:6379/0", enabled=True)
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.smembers.return_value = set()
        cache._client = mock_client

        @cached(ttl=600, cache_instance=cache)
        def fn(farm_id: str) -> str:
            return "result"

        fn(_FARM)

        mock_client.setex.assert_called()
        stored_ttl = mock_client.setex.call_args[0][1]
        assert stored_ttl == 600, f"Expected TTL=600, got {stored_ttl}"

    def test_kpi_alerts_sensor_use_separate_ttls(self) -> None:
        """kpi=300s, alerts=600s, sensor=120s each stored with correct TTL."""
        cache = AnalyticsCache("redis://localhost:6379/0", enabled=True)
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.smembers.return_value = set()
        cache._client = mock_client

        @cached(ttl=300, cache_instance=cache)
        def fn_kpi(farm_id: str) -> str:
            return "kpi"

        @cached(ttl=600, cache_instance=cache)
        def fn_alerts(farm_id: str) -> str:
            return "alerts"

        @cached(ttl=120, cache_instance=cache)
        def fn_sensor(farm_id: str) -> str:
            return "sensor"

        fn_kpi(_FARM)
        fn_alerts(_FARM)
        fn_sensor(_FARM)

        ttls = [c[0][1] for c in mock_client.setex.call_args_list]
        assert sorted(ttls) == [120, 300, 600], f"Unexpected TTLs: {ttls}"

    def test_disabled_cache_always_recomputes(self) -> None:
        """With enabled=False, every call recomputes (no Redis interaction)."""
        cache = AnalyticsCache("redis://localhost:6379/0", enabled=False)
        call_count = {"n": 0}

        @cached(ttl=300, cache_instance=cache)
        def compute(farm_id: str) -> int:
            call_count["n"] += 1
            return call_count["n"]

        compute(_FARM)
        compute(_FARM)

        assert call_count["n"] == 2, "Disabled cache must always recompute"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_redis_down_still_returns_result(self) -> None:
        """If Redis is unavailable, the function must still compute and return."""
        cache = AnalyticsCache("redis://localhost:6379/0", enabled=True)
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("Redis down")
        mock_client.setex.side_effect = ConnectionError("Redis down")
        mock_client.sadd.side_effect = ConnectionError("Redis down")
        cache._client = mock_client

        @cached(ttl=300, cache_instance=cache)
        def compute(farm_id: str) -> str:
            return "live_result"

        result = compute(_FARM)
        assert result == "live_result"

    def test_ping_returns_true_on_live_redis(self) -> None:
        cache, _ = _make_cache()
        assert cache.ping() is True

    def test_ping_returns_false_on_connection_error(self) -> None:
        cache = AnalyticsCache("redis://localhost:6379/0", enabled=True)
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("down")
        cache._client = mock_client
        assert cache.ping() is False
