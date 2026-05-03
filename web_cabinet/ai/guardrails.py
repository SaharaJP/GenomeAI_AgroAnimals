"""Input validation, output filtering, rate limiting, budget checks."""
from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger("genomeai.ai.guardrails")

_MAX_INPUT_CHARS = 2000
_MAX_OUTPUT_TOKENS = 2000
_EVIDENCE_PATTERN = re.compile(r"\[evidence:\s*\w+\]")


class GuardrailError(ValueError):
    pass


def input_sanitize(text: str) -> str:
    """Очищает входной текст: strip HTML, ограничение длины."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    if len(text) > _MAX_INPUT_CHARS:
        text = text[:_MAX_INPUT_CHARS]
        logger.warning(f"input truncated to {_MAX_INPUT_CHARS} chars")
    if not text:
        raise GuardrailError("Пустой запрос после очистки")
    return text


def output_validate(response_text: str, require_evidence: bool = False) -> str:
    """Проверяет ответ LLM: наличие evidence (если требуется), усечение по токенам."""
    if require_evidence and not _EVIDENCE_PATTERN.search(response_text):
        logger.warning("output_validate: ответ не содержит evidence-маркеров")

    # Грубая оценка токенов (~4 символа на токен) без tiktoken
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(response_text)
        if len(tokens) > _MAX_OUTPUT_TOKENS:
            truncated = enc.decode(tokens[:_MAX_OUTPUT_TOKENS])
            logger.warning(f"output truncated: {len(tokens)} → {_MAX_OUTPUT_TOKENS} tokens")
            return truncated
    except Exception:
        char_limit = _MAX_OUTPUT_TOKENS * 4
        if len(response_text) > char_limit:
            response_text = response_text[:char_limit]
            logger.warning(f"output char-truncated to {char_limit}")

    return response_text


def rate_limit_check(
    user_id: str,
    endpoint: str,
    *,
    per_min: int,
    per_hour: int,
    redis_client: Any,
) -> None:
    """Проверяет rate limit через Redis. Выбрасывает GuardrailError при превышении."""
    try:
        now = int(time.time())
        min_key = f"genomeai:rl:{user_id}:{endpoint}:min:{now // 60}"
        hour_key = f"genomeai:rl:{user_id}:{endpoint}:hour:{now // 3600}"

        pipe = redis_client.pipeline()
        pipe.incr(min_key)
        pipe.expire(min_key, 60)
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)
        results = pipe.execute()

        if results[0] > per_min:
            raise GuardrailError(f"Превышен лимит запросов: {per_min} в минуту для пользователя {user_id}")
        if results[2] > per_hour:
            raise GuardrailError(f"Превышен лимит запросов: {per_hour} в час для пользователя {user_id}")
    except GuardrailError:
        raise
    except Exception as exc:
        logger.warning(f"rate_limit_check redis error (skip): {exc}")


def check_budget(
    monthly_budget_usd: float,
    redis_client: Any,
) -> None:
    """Smoke-check: не превысили ли месячный бюджет (приблизительно через Redis счётчик)."""
    try:
        from datetime import datetime
        month_key = f"genomeai:budget:{datetime.utcnow().strftime('%Y-%m')}"
        spent_cents = redis_client.get(month_key)
        if spent_cents is None:
            return
        spent_usd = int(spent_cents) / 100.0
        if spent_usd >= monthly_budget_usd:
            logger.error(f"Месячный бюджет исчерпан: ${spent_usd:.2f} / ${monthly_budget_usd:.2f}")
            raise GuardrailError(
                f"AI временно недоступен: исчерпан месячный бюджет ${monthly_budget_usd:.2f}"
            )
    except GuardrailError:
        raise
    except Exception as exc:
        logger.warning(f"check_budget error (skip): {exc}")


def record_cost(cost_usd: float, redis_client: Any) -> None:
    """Записывает стоимость вызова в Redis бюджет-счётчик."""
    try:
        from datetime import datetime
        month_key = f"genomeai:budget:{datetime.utcnow().strftime('%Y-%m')}"
        redis_client.incrbyfloat(month_key, int(cost_usd * 100))
        redis_client.expire(month_key, 60 * 60 * 24 * 35)
    except Exception as exc:
        logger.warning(f"record_cost error: {exc}")
