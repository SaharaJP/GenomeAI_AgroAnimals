"""Redis-based cache for analytics bridges (KPI, alerts, sensor anomalies).

Uses JSON + dataclasses.asdict() for safe serialization (no binary formats).
DataFrames (raw_kpi_long) are omitted from cached values — they are supplementary
and not used by the dashboard UI.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import logging
import os
from datetime import date
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger("genomeai.analytics.cache")

try:
    import redis as _redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False


# ---------------------------------------------------------------------------
# JSON serialization helpers (safe: no binary formats)
# ---------------------------------------------------------------------------

def _to_jsonable(value: Any) -> Any:
    """Recursively convert analytics return values to JSON-serializable form."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        d: dict[str, Any] = {}
        for f in dataclasses.fields(value):
            v = getattr(value, f.name)
            # Skip DataFrames — supplementary data, not needed in cache
            if hasattr(v, "to_dict") and hasattr(v, "iloc"):
                d[f.name] = None
            else:
                d[f.name] = _to_jsonable(v)
        return {
            "__dc__": type(value).__qualname__,
            "__module__": type(value).__module__,
            "data": d,
        }
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, list):
        return [_to_jsonable(i) for i in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def _from_jsonable(value: Any) -> Any:
    """Reconstruct analytics return values from JSON-deserialized dicts."""
    if isinstance(value, dict):
        if "__dc__" in value:
            import importlib
            mod = importlib.import_module(value["__module__"])
            # Handle nested qualnames (e.g. "Outer.Inner")
            cls: Any = mod
            for part in value["__dc__"].split("."):
                cls = getattr(cls, part)
            kwargs = {k: _from_jsonable(v) for k, v in value["data"].items()}
            return cls(**kwargs)
        if "__date__" in value:
            return date.fromisoformat(value["__date__"])
        return {k: _from_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_jsonable(i) for i in value]
    return value


def _serialize(value: Any) -> str:
    return json.dumps(_to_jsonable(value), ensure_ascii=False)


def _deserialize(raw: str) -> Any:
    return _from_jsonable(json.loads(raw))


# ---------------------------------------------------------------------------
# AnalyticsCache
# ---------------------------------------------------------------------------

class AnalyticsCache:
    """Redis-backed cache for analytics bridge results.

    Graceful degradation: Redis errors are logged and the underlying function
    is called normally, so the service degrades without failing.

    Farm-level invalidation uses a secondary index (Redis SET per farm_id)
    to track which cache keys belong to each farm.
    """

    KEY_PREFIX = "genomeai:analytics:"
    FARM_INDEX_PREFIX = "genomeai:analytics:farm:"
    INVALIDATION_CHANNEL = "genomeai:analytics:invalidate"

    def __init__(self, redis_url: str, enabled: bool = True) -> None:
        self._redis_url = redis_url
        self._enabled = enabled
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            if not _HAS_REDIS:
                raise RuntimeError("redis package not installed")
            self._client = _redis_lib.from_url(self._redis_url, decode_responses=True)
        return self._client

    def make_key(self, namespace: str, params: dict) -> str:
        """Deterministic cache key: prefix + SHA256(namespace + sorted params)."""
        raw = namespace + "::" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return self.KEY_PREFIX + hashlib.sha256(raw.encode()).hexdigest()

    def _farm_index_key(self, farm_id: str) -> str:
        return f"{self.FARM_INDEX_PREFIX}{farm_id}"

    def get_value(self, key: str) -> Optional[Any]:
        if not self._enabled:
            return None
        try:
            raw = self._get_client().get(key)
            if raw is None:
                return None
            logger.debug("cache hit: %s", key[:40])
            return _deserialize(raw)
        except Exception as exc:
            logger.warning("cache.get error (degraded): %s", exc)
            return None

    def set_value(self, key: str, value: Any, ttl: int, farm_id: Optional[str] = None) -> None:
        if not self._enabled:
            return
        try:
            client = self._get_client()
            client.setex(key, ttl, _serialize(value))
            if farm_id:
                idx = self._farm_index_key(farm_id)
                client.sadd(idx, key)
                client.expire(idx, ttl + 60)
        except Exception as exc:
            logger.warning("cache.set error (degraded): %s", exc)

    def invalidate_farm(self, farm_id: str) -> None:
        """Delete all cached entries for farm_id and the farm index set."""
        try:
            client = self._get_client()
            idx = self._farm_index_key(farm_id)
            keys = client.smembers(idx)
            if keys:
                client.delete(idx, *keys)
            else:
                client.delete(idx)
        except Exception as exc:
            logger.warning("cache.invalidate_farm error: %s", exc)

    def publish_invalidation(self, farm_id: str) -> None:
        """Publish an invalidation event so other processes can clear their caches."""
        try:
            msg = json.dumps({"farm_id": farm_id})
            self._get_client().publish(self.INVALIDATION_CHANNEL, msg)
        except Exception as exc:
            logger.warning("cache.publish error (degraded): %s", exc)

    def ping(self) -> bool:
        try:
            self._get_client().ping()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_cache_instance: Optional[AnalyticsCache] = None


def get_analytics_cache() -> AnalyticsCache:
    global _cache_instance
    if _cache_instance is None:
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        enabled = os.getenv("GENOMEAI_ANALYTICS_CACHE_ENABLED", "true").lower() == "true"
        _cache_instance = AnalyticsCache(redis_url=redis_url, enabled=enabled)
    return _cache_instance


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------

def cached(
    ttl: int,
    namespace: str = "",
    cache_instance: Optional[AnalyticsCache] = None,
) -> Callable:
    """Cache decorator for analytics bridge functions.

    Cache key = namespace (defaults to function name) + all bound arguments.
    If the function has a `farm_id` parameter, its value is indexed for fast
    farm-level invalidation via invalidate_farm().
    """
    def decorator(fn: Callable) -> Callable:
        _ns = namespace or fn.__name__
        sig = inspect.signature(fn)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _cache = cache_instance or get_analytics_cache()

            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Normalize all args to JSON-serializable primitives for key building
            params: dict[str, Any] = {}
            for k, v in bound.arguments.items():
                if isinstance(v, date):
                    params[k] = v.isoformat()
                elif isinstance(v, (str, int, float, bool, type(None))):
                    params[k] = v
                else:
                    params[k] = str(v)

            key = _cache.make_key(_ns, params)
            hit = _cache.get_value(key)
            if hit is not None:
                return hit

            result = fn(*args, **kwargs)
            farm_id: Optional[str] = bound.arguments.get("farm_id")
            _cache.set_value(key, result, ttl, farm_id=farm_id)
            return result

        return wrapper
    return decorator
