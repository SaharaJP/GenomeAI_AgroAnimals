"""Unit tests for SSE graceful shutdown signal in insights_stream module.

Spec: docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md

Tests use synchronous wrappers (asyncio.new_event_loop) because the repo
does not depend on pytest-asyncio.
"""
from __future__ import annotations

import asyncio

import pytest

from web_cabinet.ai.endpoints import insights_stream as ism


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _reset_shutdown_event():
    if hasattr(ism, "_shutdown_event"):
        ism._shutdown_event.clear()
    yield
    if hasattr(ism, "_shutdown_event"):
        ism._shutdown_event.clear()


def test_generator_blocks_when_idle():
    async def _scenario():
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
        ism._subscribers.add(q)
        gen = ism._event_generator(q)
        try:
            first = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
            assert first.startswith(": connected")
            # Idleness check: start __anext__ as a task and observe that it
            # does not complete within 50 ms while the queue is empty and
            # shutdown is not signalled. We avoid asyncio.wait_for here
            # because the generator's existing `except CancelledError: pass`
            # would convert the cancellation into a clean return, surfacing
            # as StopAsyncIteration rather than TimeoutError.
            task = asyncio.create_task(gen.__anext__())
            await asyncio.sleep(0.05)
            assert not task.done(), "generator should still be blocked"
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        finally:
            await gen.aclose()
    _run(_scenario())


def test_signal_shutdown_completes_generator_fast():
    async def _scenario():
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
        ism._subscribers.add(q)
        gen = ism._event_generator(q)
        # Consume the initial "connected" frame.
        await asyncio.wait_for(gen.__anext__(), timeout=0.5)

        ism.signal_shutdown()

        loop = asyncio.get_running_loop()
        t0 = loop.time()
        # Tight timeout doubles as the perf budget: signal_shutdown() must
        # wake the generator and complete the StopAsyncIteration handoff
        # within 50ms on any reasonable host.
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(gen.__anext__(), timeout=0.05)
        elapsed = loop.time() - t0
        assert elapsed < 0.05, f"generator took {elapsed:.3f}s to exit"
        # Subscriber must be removed by the generator's finally block.
        assert q not in list(ism._subscribers)
    _run(_scenario())


def test_signal_shutdown_is_idempotent():
    ism.signal_shutdown()
    ism.signal_shutdown()
    # No exception expected; event stays set.
    assert ism._shutdown_event.is_set()


def test_new_connection_during_shutdown_exits_immediately():
    async def _scenario():
        ism.signal_shutdown()
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
        ism._subscribers.add(q)
        gen = ism._event_generator(q)
        # Initial "connected" frame still yielded.
        first = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
        assert first.startswith(": connected")
        # Next call should immediately raise StopAsyncIteration.
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(gen.__anext__(), timeout=0.1)
        assert q not in list(ism._subscribers)
    _run(_scenario())
