"""Anthropic API client с retry, prompt caching и structured logging."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, AsyncIterator, Optional

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

from .config import get_ai_settings

logger = logging.getLogger("genomeai.ai.client")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class LLMResponse:
    def __init__(
        self,
        content: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_tokens = cache_creation_tokens
        self.cache_read_tokens = cache_read_tokens
        self.latency_ms = latency_ms

    @property
    def cache_hit(self) -> bool:
        return self.cache_read_tokens > 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class AnthropicClient:
    """Единый клиент для всех AI-вызовов GenomeAI.

    Использует prompt caching на system prompts и farm_context для снижения стоимости.
    Все вызовы логируются как structured JSON для observability.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._settings = get_ai_settings()
        self._api_key = api_key or self._settings.ANTHROPIC_API_KEY
        self._client: Any = None
        self._async_client: Any = None

    def _get_client(self) -> Any:
        if not _HAS_ANTHROPIC:
            raise RuntimeError("Пакет anthropic не установлен. Выполните: pip install anthropic>=0.40")
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _get_async_client(self) -> Any:
        if not _HAS_ANTHROPIC:
            raise RuntimeError("Пакет anthropic не установлен. Выполните: pip install anthropic>=0.40")
        if self._async_client is None:
            self._async_client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._async_client

    def _build_system_blocks(self, system_prompt: str, farm_context: Optional[str] = None) -> list[dict]:
        """Строит system blocks с cache_control для экономии токенов."""
        blocks: list[dict] = []

        if farm_context:
            blocks.append({
                "type": "text",
                "text": system_prompt,
            })
            blocks.append({
                "type": "text",
                "text": f"<farm_context>\n{farm_context}\n</farm_context>",
                "cache_control": {"type": "ephemeral"},
            })
        else:
            blocks.append({
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            })

        return blocks

    def _log_call(
        self,
        model: str,
        task_type: str,
        response: Optional[LLMResponse],
        user_id: Optional[str],
        error: Optional[str] = None,
        *,
        endpoint: str = "unknown",
        prompt: Optional[str] = None,
        evidence_chips: Optional[list] = None,
        tools_used: Optional[list] = None,
    ) -> None:
        record = {
            "event": "llm_call",
            "model": model,
            "task_type": task_type,
            "user_id": user_id,
            "endpoint": endpoint,
            "input_tokens": response.input_tokens if response else 0,
            "output_tokens": response.output_tokens if response else 0,
            "cache_hit": response.cache_hit if response else False,
            "cache_creation_tokens": response.cache_creation_tokens if response else 0,
            "cache_read_tokens": response.cache_read_tokens if response else 0,
            "latency_ms": response.latency_ms if response else 0,
            "error": error,
        }
        logger.info(json.dumps(record, ensure_ascii=False))

        # Best-effort persistence to ai_call_log (sync, swallows all errors).
        try:
            from core.infra.postgres_compat import connect_postgres_compat
            from .call_log import persist_ai_call

            conn = connect_postgres_compat()
            try:
                persist_ai_call(
                    conn=conn,
                    endpoint=endpoint,
                    task_type=task_type,
                    model=model,
                    user_id=user_id,
                    input_tokens=response.input_tokens if response else 0,
                    output_tokens=response.output_tokens if response else 0,
                    cache_creation_tokens=response.cache_creation_tokens if response else 0,
                    cache_read_tokens=response.cache_read_tokens if response else 0,
                    latency_ms=int(response.latency_ms) if response else 0,
                    error=error,
                    prompt=prompt,
                    response=response.content if response else None,
                    evidence_chips=evidence_chips,
                    tools_used=tools_used,
                )
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("ai_call_log connect failed: %s", exc)

    def _model_for_task(self, task_type: str) -> str:
        return self._settings.model_for_task(task_type)

    def generate(
        self,
        user_message: str,
        *,
        system_prompt: str = "",
        farm_context: Optional[str] = None,
        task_type: str = "default",
        model: Optional[str] = None,
        max_tokens: int = 1024,
        user_id: str = "system",
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Синхронный generate с retry и prompt caching."""
        target_model = model or self._model_for_task(task_type)
        client = self._get_client()

        system_blocks = self._build_system_blocks(system_prompt, farm_context) if system_prompt else []
        messages = [{"role": "user", "content": user_message}]

        last_error: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                t0 = time.monotonic()
                kwargs: dict[str, Any] = dict(
                    model=target_model,
                    max_tokens=max_tokens,
                    messages=messages,
                )
                if system_blocks:
                    kwargs["system"] = system_blocks

                response = client.messages.create(**kwargs)
                latency_ms = (time.monotonic() - t0) * 1000

                usage = response.usage
                result = LLMResponse(
                    content=response.content[0].text,
                    model=response.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                    latency_ms=latency_ms,
                )
                self._log_call(
                    target_model, task_type, result, user_id,
                    endpoint=task_type, prompt=user_message,
                )
                return result

            except Exception as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status not in _RETRYABLE_STATUS and not _is_transient(exc):
                    break
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    json.dumps({
                        "event": "llm_retry",
                        "attempt": attempt + 1,
                        "delay_s": delay,
                        "error": str(exc),
                        "task_type": task_type,
                    })
                )
                time.sleep(delay)

        dummy = LLMResponse("", target_model, 0, 0)
        self._log_call(
            target_model, task_type, dummy, user_id,
            error=str(last_error), endpoint=task_type, prompt=user_message,
        )
        raise last_error  # type: ignore[misc]

    async def agenerate(
        self,
        user_message: str,
        *,
        system_prompt: str = "",
        farm_context: Optional[str] = None,
        task_type: str = "default",
        model: Optional[str] = None,
        max_tokens: int = 1024,
        user_id: str = "system",
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Асинхронный generate с retry и prompt caching."""
        target_model = model or self._model_for_task(task_type)
        client = self._get_async_client()

        system_blocks = self._build_system_blocks(system_prompt, farm_context) if system_prompt else []
        messages = [{"role": "user", "content": user_message}]

        last_error: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                t0 = time.monotonic()
                kwargs: dict[str, Any] = dict(
                    model=target_model,
                    max_tokens=max_tokens,
                    messages=messages,
                )
                if system_blocks:
                    kwargs["system"] = system_blocks

                response = await client.messages.create(**kwargs)
                latency_ms = (time.monotonic() - t0) * 1000

                usage = response.usage
                result = LLMResponse(
                    content=response.content[0].text,
                    model=response.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                    latency_ms=latency_ms,
                )
                self._log_call(
                    target_model, task_type, result, user_id,
                    endpoint=task_type, prompt=user_message,
                )
                return result

            except Exception as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status not in _RETRYABLE_STATUS and not _is_transient(exc):
                    break
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    json.dumps({
                        "event": "llm_retry",
                        "attempt": attempt + 1,
                        "delay_s": delay,
                        "error": str(exc),
                        "task_type": task_type,
                    })
                )
                await asyncio.sleep(delay)

        dummy = LLMResponse("", target_model, 0, 0)
        self._log_call(
            target_model, task_type, dummy, user_id,
            error=str(last_error), endpoint=task_type, prompt=user_message,
        )
        raise last_error  # type: ignore[misc]

    async def astream(
        self,
        user_message: str,
        *,
        system_prompt: str = "",
        farm_context: Optional[str] = None,
        task_type: str = "default",
        model: Optional[str] = None,
        max_tokens: int = 2048,
        user_id: str = "system",
    ) -> AsyncIterator[str]:
        """Streaming generate для SSE endpoints."""
        target_model = model or self._model_for_task(task_type)
        client = self._get_async_client()

        system_blocks = self._build_system_blocks(system_prompt, farm_context) if system_prompt else []
        messages = [{"role": "user", "content": user_message}]

        kwargs: dict[str, Any] = dict(
            model=target_model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system_blocks:
            kwargs["system"] = system_blocks

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def tool_call(
        self,
        user_message: str,
        tools: list[dict],
        *,
        system_prompt: str = "",
        farm_context: Optional[str] = None,
        task_type: str = "default",
        model: Optional[str] = None,
        max_tokens: int = 2048,
        user_id: str = "system",
    ) -> LLMResponse:
        """Tool use call для structured data retrieval."""
        target_model = model or self._model_for_task(task_type)
        client = self._get_async_client()

        system_blocks = self._build_system_blocks(system_prompt, farm_context) if system_prompt else []
        messages = [{"role": "user", "content": user_message}]

        t0 = time.monotonic()
        kwargs: dict[str, Any] = dict(
            model=target_model,
            max_tokens=max_tokens,
            tools=tools,
            messages=messages,
        )
        if system_blocks:
            kwargs["system"] = system_blocks

        response = await client.messages.create(**kwargs)
        latency_ms = (time.monotonic() - t0) * 1000

        content_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        usage = response.usage
        result = LLMResponse(
            content=content_text,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            latency_ms=latency_ms,
        )
        self._log_call(target_model, task_type, result, user_id)
        return result


def _is_transient(exc: Exception) -> bool:
    """Определяет, является ли ошибка transient (подходит для retry)."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return any(kw in name or kw in msg for kw in ("timeout", "connect", "network", "rate"))


_default_client: Optional[AnthropicClient] = None


def get_client() -> AnthropicClient:
    global _default_client
    if _default_client is None:
        _default_client = AnthropicClient()
    return _default_client
