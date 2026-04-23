"""Redis-based session memory для AI Q&A (ask-farm)."""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger("genomeai.ai.session_memory")

_MAX_MESSAGES = 10
_SESSION_TTL = 3600  # 1 час


class SessionMemory:
    """Хранит историю сообщений сессии в Redis. Graceful degradation при недоступности."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: Optional[object] = None

    def _get_client(self):
        if self._client is None:
            try:
                import redis  # type: ignore
                self._client = redis.from_url(self._redis_url, decode_responses=True)
            except ImportError:
                raise RuntimeError("Пакет redis не установлен")
        return self._client

    @staticmethod
    def _key(session_id: str) -> str:
        return f"ai:session:{session_id}"

    def load(self, session_id: str) -> list[dict]:
        """Загружает историю сообщений. Возвращает [] при ошибке."""
        try:
            raw = self._get_client().get(self._key(session_id))
            if raw is None:
                return []
            return json.loads(raw)
        except Exception as exc:
            logger.warning(f"session_memory.load error: {exc}")
            return []

    def append(self, session_id: str, role: str, content: str) -> list[dict]:
        """Добавляет сообщение. Обрезает до _MAX_MESSAGES. Возвращает итоговый список."""
        messages = self.load(session_id)
        messages.append({"role": role, "content": content})
        if len(messages) > _MAX_MESSAGES:
            messages = messages[-_MAX_MESSAGES:]
        self._save(session_id, messages)
        return messages

    def _save(self, session_id: str, messages: list[dict]) -> None:
        try:
            self._get_client().setex(
                self._key(session_id),
                _SESSION_TTL,
                json.dumps(messages, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning(f"session_memory.save error: {exc}")


_instance: Optional[SessionMemory] = None


def get_session_memory() -> SessionMemory:
    global _instance
    if _instance is None:
        from .config import get_ai_settings
        _instance = SessionMemory(get_ai_settings().REDIS_URL)
    return _instance
