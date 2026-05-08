"""Best-effort persistence of LLM call records into ai_call_log."""
from __future__ import annotations

import json
import logging
from typing import Any

from .pricing import compute_cost_usd

logger = logging.getLogger("genomeai.ai.call_log")

_MAX_TEXT_BYTES = 50_000


def _truncate(text: str | None) -> str | None:
    if text is None:
        return None
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_TEXT_BYTES:
        return text
    kb = len(encoded) // 1024
    body = encoded[:_MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    return f"[TRUNCATED:{kb}kb]\n{body}"


def persist_ai_call(
    *,
    conn: Any,
    endpoint: str,
    task_type: str,
    model: str,
    user_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    latency_ms: float,
    error: str | None,
    prompt: str | None,
    response: str | None,
    evidence_chips: list[str] | None,
    tools_used: list[dict] | None,
) -> None:
    """Insert one row into ai_call_log. Never raises."""
    try:
        cost = compute_cost_usd(
            model, input_tokens, output_tokens,
            cache_creation_tokens, cache_read_tokens,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_call_log (
                    user_id, endpoint, task_type, model,
                    input_tokens, output_tokens,
                    cache_creation_tokens, cache_read_tokens,
                    cost_usd, latency_ms, error,
                    prompt, response, evidence_chips, tools_used
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb
                )
                """,
                (
                    user_id, endpoint, task_type, model,
                    int(input_tokens), int(output_tokens),
                    int(cache_creation_tokens), int(cache_read_tokens),
                    float(cost), int(latency_ms), error,
                    _truncate(prompt), _truncate(response),
                    json.dumps(evidence_chips or [], ensure_ascii=False),
                    json.dumps(tools_used or [], ensure_ascii=False),
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("ai_call_log persist failed: %s", exc)
