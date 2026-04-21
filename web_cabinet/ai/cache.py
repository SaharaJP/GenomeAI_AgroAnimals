"""Redis-based кэш для AI-ответов."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("genomeai.ai.cache")

try:
    import redis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False


class AICache:
    """Redis-кэш для AI-ответов. Graceful degradation при недоступности Redis."""

    def __init__(self, redis_url: str, ttl_seconds: int = 300, enabled: bool = True) -> None:
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._enabled = enabled
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            if not _HAS_REDIS:
                raise RuntimeError("Пакет redis не установлен")
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def make_key(endpoint: str, params: dict) -> str:
        raw = endpoint + "::" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return "genomeai:ai:" + hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Optional[str]:
        if not self._enabled:
            return None
        try:
            client = self._get_client()
            value = client.get(key)
            if value:
                logger.debug(f"cache hit: {key[:32]}...")
            return value
        except Exception as exc:
            logger.warning(f"cache.get error (degraded): {exc}")
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        if not self._enabled:
            return
        try:
            client = self._get_client()
            client.setex(key, ttl or self._ttl, value)
        except Exception as exc:
            logger.warning(f"cache.set error (degraded): {exc}")

    def invalidate(self, key: str) -> None:
        try:
            client = self._get_client()
            client.delete(key)
        except Exception as exc:
            logger.warning(f"cache.invalidate error: {exc}")

    def get_json(self, endpoint: str, params: dict) -> Optional[Any]:
        key = self.make_key(endpoint, params)
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, endpoint: str, params: dict, value: Any, ttl: Optional[int] = None) -> None:
        key = self.make_key(endpoint, params)
        self.set(key, json.dumps(value, ensure_ascii=False), ttl)

    def ping(self) -> bool:
        try:
            self._get_client().ping()
            return True
        except Exception:
            return False


_cache_instance: Optional[AICache] = None


def get_cache() -> AICache:
    global _cache_instance
    if _cache_instance is None:
        from .config import get_ai_settings
        settings = get_ai_settings()
        _cache_instance = AICache(
            redis_url=settings.REDIS_URL,
            ttl_seconds=settings.GENOMEAI_AI_CACHE_TTL_SECONDS,
            enabled=settings.GENOMEAI_AI_ENABLE_CACHE,
        )
    return _cache_instance
