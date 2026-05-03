"""GET /api/ai/insights/events/stream — SSE-уведомления о новых инсайтах (MVP-N15).

Клиент держит соединение открытым. Когда insight_scanner создаёт инсайты,
broadcast_insights_event() пушит событие во все открытые соединения.
"""
from __future__ import annotations

import asyncio
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
    """Генератор для StreamingResponse: heartbeat + события из очереди."""
    yield ": connected\n\n"
    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
                yield data
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
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
