"""GET /api/ai/insights/events/stream — SSE-уведомления о новых инсайтах (MVP-N15).

Клиент держит соединение открытым. Когда insight_scanner создаёт инсайты,
broadcast_insights_event() пушит событие во все открытые соединения.

При shutdown FastAPI lifespan хук вызывает signal_shutdown(), что приводит
к корректному выходу всех активных _event_generator корутин (см.
docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import weakref
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger("genomeai.ai.endpoint.insights_stream")
router = APIRouter()

# In-process pub/sub: слабые ссылки на asyncio.Queue каждого SSE-клиента.
_subscribers: weakref.WeakSet["asyncio.Queue[str]"] = weakref.WeakSet()
_KEEPALIVE_INTERVAL = 25  # секунд между heartbeat-комментариями

# Module-level shutdown signal. Set by FastAPI lifespan shutdown handler;
# observed by every active _event_generator coroutine to exit cleanly.
_shutdown_event: asyncio.Event = asyncio.Event()


def signal_shutdown() -> None:
    """Сигнализирует всем активным _event_generator корутинам выйти.

    Идемпотентен. Вызывается из FastAPI lifespan shutdown handler.
    """
    _shutdown_event.set()


def broadcast_insights_event(farm_id: str, count: int) -> None:
    """Пушит событие new_insights во все активные SSE-соединения.

    Вызывается из background-потока APScheduler (thread-safe через call_soon_threadsafe).
    """
    payload = json.dumps({"event": "new_insights", "farm_id": farm_id, "count": count})
    sse_data = f"data: {payload}\n\n"
    dead: list["asyncio.Queue[str]"] = []
    for q in list(_subscribers):
        try:
            q.put_nowait(sse_data)
        except asyncio.QueueFull:
            dead.append(q)
    if dead:
        logger.debug(f"SSE: {len(dead)} slow clients dropped")


async def _event_generator(queue: "asyncio.Queue[str]") -> AsyncIterator[str]:
    """Генератор для StreamingResponse: heartbeat + события + graceful shutdown.

    Гонит queue.get() против _shutdown_event.wait() с таймаутом
    _KEEPALIVE_INTERVAL. При срабатывании shutdown_event — выходит из цикла
    и удаляет subscriber в finally.
    """
    yield ": connected\n\n"
    if _shutdown_event.is_set():
        try:
            _subscribers.discard(queue)
        except Exception:
            pass
        return

    shutdown_task = asyncio.create_task(_shutdown_event.wait())
    get_task: asyncio.Task[str] | None = None
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {get_task, shutdown_task},
                timeout=_KEEPALIVE_INTERVAL,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shutdown_task in done:
                get_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await get_task
                get_task = None
                break
            if get_task in done:
                payload = get_task.result()
                get_task = None
                yield payload
            else:
                # Periodic keepalive prevents intermediate proxies (nginx,
                # browsers) from dropping an idle SSE connection as stale.
                get_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await get_task
                get_task = None
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        # Re-raise per asyncio 3.8+ convention; the finally block below
        # handles all cleanup unconditionally.
        raise
    finally:
        if get_task is not None and not get_task.done():
            get_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await get_task
        if not shutdown_task.done():
            shutdown_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await shutdown_task
        try:
            _subscribers.discard(queue)
        except Exception:
            pass


@router.get("/insights/events/stream")
async def insights_event_stream(farm_id: str = "demo-farm-v1") -> StreamingResponse:
    """SSE endpoint для push-уведомлений об инсайтах.

    Клиент (frontend) держит соединение открытым.
    При появлении новых инсайтов приходит событие:
      data: {"event": "new_insights", "farm_id": "...", "count": 3}
    """
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    _subscribers.add(queue)
    logger.debug(f"SSE client connected farm={farm_id} subscribers={len(_subscribers)}")
    return StreamingResponse(
        _event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
