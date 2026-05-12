# SSE Graceful Shutdown — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate uvicorn hang on SIGTERM caused by long-lived SSE streams; backend must exit within seconds, not block indefinitely.

**Architecture:** App-level — `asyncio.Event` set from FastAPI lifespan shutdown handler wakes up all `_event_generator` coroutines via `asyncio.wait(FIRST_COMPLETED)`, they exit cleanly and discard their subscribers. Process-level safety-net — uvicorn launched with `--timeout-graceful-shutdown=10` (configurable via `GENOMEAI_WEB_SHUTDOWN_TIMEOUT`).

**Tech Stack:** Python 3.12, FastAPI, Starlette, uvicorn 0.46, pytest-asyncio. Repo root: `/opt/genomeai/repo`. Canonical paths per CLAUDE.md — `web_cabinet/` (top-level), `src/genomeai/`, `src/core/`.

**Spec:** `docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md`

---

## File Structure

| File | Role | Action |
|---|---|---|
| `web_cabinet/ai/endpoints/insights_stream.py` | SSE endpoint + shutdown event + generator | Modify |
| `web_cabinet/app.py` | FastAPI app; lifespan `_shutdown()` (line ~606) | Modify (1 block) |
| `src/genomeai/app_launcher.py` | Canonical backend launcher; `cmd_backend` (line ~86) | Modify (1 block) |
| `tests/test_insights_stream_shutdown.py` | Unit test for shutdown event | Create |
| `scripts/smoke_sse_shutdown.py` | Subprocess smoke proof | Create |
| `docs/operations_runbook.md` | Mention `GENOMEAI_WEB_SHUTDOWN_TIMEOUT` env | Modify (append section) |
| `artifacts/_ci/sse_shutdown_smoke.log` | Proof artifact (produced by smoke run) | Create at runtime |
| `docs/iterations/2026-05-12-sse-graceful-shutdown_execution_proof.md` | Iteration proof | Create at end |

---

## Task 1: Verify uvicorn version supports the flag

**Files:** none (verification only).

- [ ] **Step 1: Confirm uvicorn ≥ 0.18 (flag introduced)**

Run:
```bash
.venv/bin/python -c "import uvicorn; v=uvicorn.__version__; print(v); assert tuple(int(x) for x in v.split('.')[:2]) >= (0, 18), 'too old'"
```

Expected: prints `0.46.0` (current) without assertion error.

If older: stop and report — plan needs an upgrade task before proceeding.

---

## Task 2: Failing unit test for idle generator + shutdown signal

**Files:**
- Create: `tests/test_insights_stream_shutdown.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_insights_stream_shutdown.py`:
```python
"""Unit tests for SSE graceful shutdown signal in insights_stream module.

Spec: docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md
"""
from __future__ import annotations

import asyncio

import pytest

from web_cabinet.ai.endpoints import insights_stream as ism


@pytest.fixture(autouse=True)
def _reset_shutdown_event():
    # Module-level event is shared state across tests — reset before and after.
    if hasattr(ism, "_shutdown_event"):
        ism._shutdown_event.clear()
    yield
    if hasattr(ism, "_shutdown_event"):
        ism._shutdown_event.clear()


@pytest.mark.asyncio
async def test_generator_blocks_when_idle():
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    ism._subscribers.add(q)
    gen = ism._event_generator(q)
    try:
        first = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
        assert first.startswith(": connected")
        # Should NOT yield more within 50 ms while queue is empty
        # and shutdown not signalled.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gen.__anext__(), timeout=0.05)
    finally:
        await gen.aclose()


@pytest.mark.asyncio
async def test_signal_shutdown_completes_generator_fast():
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    ism._subscribers.add(q)
    gen = ism._event_generator(q)
    # Consume the initial "connected" frame.
    await asyncio.wait_for(gen.__anext__(), timeout=0.5)

    ism.signal_shutdown()

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=0.2)
    elapsed = loop.time() - t0
    assert elapsed < 0.2, f"generator took {elapsed:.3f}s to exit"
    # Subscriber must be removed by the generator's finally block.
    assert q not in list(ism._subscribers)


@pytest.mark.asyncio
async def test_signal_shutdown_is_idempotent():
    ism.signal_shutdown()
    ism.signal_shutdown()
    # No exception expected; event stays set.
    assert ism._shutdown_event.is_set()


@pytest.mark.asyncio
async def test_new_connection_during_shutdown_exits_immediately():
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_insights_stream_shutdown.py -v 2>&1 | tail -30
```

Expected: 3 of 4 tests fail with `AttributeError: module 'web_cabinet.ai.endpoints.insights_stream' has no attribute 'signal_shutdown'` (or `_shutdown_event`). The first test (`test_generator_blocks_when_idle`) may pass with current code — that is OK; it is the no-regression guard for existing behavior.

- [ ] **Step 3: Do not commit yet — implementation comes next.**

---

## Task 3: Implement shutdown event + signal_shutdown + new generator

**Files:**
- Modify: `web_cabinet/ai/endpoints/insights_stream.py`

- [ ] **Step 1: Read current file**

Run:
```bash
cat web_cabinet/ai/endpoints/insights_stream.py
```

Confirm it matches the snapshot from the spec (function `_event_generator` lines 42–58, no `_shutdown_event`).

- [ ] **Step 2: Rewrite the file**

Replace entire contents of `web_cabinet/ai/endpoints/insights_stream.py` with:
```python
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
                break
            if get_task in done:
                yield get_task.result()
            else:
                # Timeout без событий — heartbeat.
                get_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await get_task
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
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
```

- [ ] **Step 3: Run unit tests; verify all pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_insights_stream_shutdown.py -v 2>&1 | tail -20
```

Expected: 4 passed.

- [ ] **Step 4: Commit (test + impl together)**

```bash
git add tests/test_insights_stream_shutdown.py web_cabinet/ai/endpoints/insights_stream.py
git commit -m "$(cat <<'EOF'
feat(sse): graceful shutdown event for /insights/events/stream

Adds module-level _shutdown_event + signal_shutdown() in insights_stream.
_event_generator now races queue.get() against the event via
asyncio.wait(FIRST_COMPLETED), exits within ms when signalled, and
discards its subscriber from the WeakSet.

Spec: docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md
Tests: tests/test_insights_stream_shutdown.py (4 cases).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire signal_shutdown() into FastAPI lifespan shutdown

**Files:**
- Modify: `web_cabinet/app.py:606-630` (function `_shutdown()`)

- [ ] **Step 1: Read context around the function**

Run:
```bash
sed -n '600,640p' web_cabinet/app.py
```

Confirm the existing `_shutdown()` ends at line ~630 with three try-blocks stopping crons; immediately followed by `@asynccontextmanager` for `_lifespan`.

- [ ] **Step 2: Insert SSE shutdown signal at the end of `_shutdown()`**

Use Edit tool to append a new try-block after the `stop_weekly_brief_cron()` block. The exact old_string and new_string:

old_string:
```python
    try:
        from web_cabinet.ai.background.weekly_brief_cron import stop_cron as stop_weekly_brief_cron
        stop_weekly_brief_cron()
    except Exception:
        pass


@asynccontextmanager
```

new_string:
```python
    try:
        from web_cabinet.ai.background.weekly_brief_cron import stop_cron as stop_weekly_brief_cron
        stop_weekly_brief_cron()
    except Exception:
        pass

    try:
        from web_cabinet.ai.endpoints.insights_stream import signal_shutdown as _sse_signal_shutdown
        _sse_signal_shutdown()
    except Exception:
        pass


@asynccontextmanager
```

- [ ] **Step 3: Smoke-import the app to catch syntax errors**

Run:
```bash
.venv/bin/python -c "from web_cabinet.app import app; print('OK', type(app).__name__)"
```

Expected: prints `OK FastAPI`.

- [ ] **Step 4: Commit**

```bash
git add web_cabinet/app.py
git commit -m "$(cat <<'EOF'
feat(app): call insights_stream.signal_shutdown() on lifespan shutdown

Ensures all live SSE generators on /api/ai/insights/events/stream exit
cleanly when FastAPI lifespan tears down, so uvicorn graceful shutdown
does not hang waiting for them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add uvicorn `--timeout-graceful-shutdown` flag (safety-net)

**Files:**
- Modify: `src/genomeai/app_launcher.py:86-95` (block constructing `cmd_backend`)

- [ ] **Step 1: Read current cmd_backend block**

Run:
```bash
sed -n '80,100p' src/genomeai/app_launcher.py
```

Confirm `cmd_backend = [sys.executable, "-m", "uvicorn", "web_cabinet.app:app", "--host", args.host, "--port", str(args.backend_port)]` exists exactly.

- [ ] **Step 2: Insert env-driven timeout flag**

Use Edit. old_string:
```python
    cmd_backend = [
        sys.executable,
        "-m",
        "uvicorn",
        "web_cabinet.app:app",
        "--host",
        args.host,
        "--port",
        str(args.backend_port),
    ]
```

new_string:
```python
    _shutdown_timeout = os.environ.get("GENOMEAI_WEB_SHUTDOWN_TIMEOUT", "10")
    cmd_backend = [
        sys.executable,
        "-m",
        "uvicorn",
        "web_cabinet.app:app",
        "--host",
        args.host,
        "--port",
        str(args.backend_port),
        "--timeout-graceful-shutdown",
        _shutdown_timeout,
    ]
```

- [ ] **Step 3: Verify dry-run prints the new flag**

Run:
```bash
.venv/bin/python -m genomeai.app_launcher --dry-run 2>&1 | grep -E "BACKEND|timeout-graceful"
```

Expected: line `BACKEND: ... --timeout-graceful-shutdown 10`.

- [ ] **Step 4: Commit**

```bash
git add src/genomeai/app_launcher.py
git commit -m "$(cat <<'EOF'
feat(launcher): pass --timeout-graceful-shutdown=10 to uvicorn

Safety-net for SSE/streaming hangs on SIGTERM. Configurable via env
GENOMEAI_WEB_SHUTDOWN_TIMEOUT. App-level fix in insights_stream usually
makes shutdown complete in <1s; this flag bounds the worst case.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Smoke-proof script — real uvicorn + SIGTERM

**Files:**
- Create: `scripts/smoke_sse_shutdown.py`

- [ ] **Step 1: Write the script**

Create `scripts/smoke_sse_shutdown.py`:
```python
#!/usr/bin/env python3
"""Smoke-proof: uvicorn must exit within 3s of SIGTERM with an open SSE stream.

Spawns uvicorn on a free port, opens an SSE connection to /api/ai/insights/events/stream,
reads the ": connected" frame to ensure the generator is engaged, then sends SIGTERM
to the uvicorn process and measures wall-time until process exit.

Writes a single-line result to artifacts/_ci/sse_shutdown_smoke.log:
  OK   elapsed=<sec> at <iso-ts>     — pass
  FAIL elapsed=<sec> at <iso-ts> ... — fail (also exit code 1)

Usage:
  python scripts/smoke_sse_shutdown.py
"""
from __future__ import annotations

import datetime as _dt
import http.client as _http
import os
import pathlib
import signal
import socket
import subprocess
import sys
import threading
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = REPO_ROOT / "artifacts" / "_ci" / "sse_shutdown_smoke.log"
ACCEPTANCE_SEC = 3.0
HARD_TIMEOUT_SEC = 15.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _read_sse_connected(host: str, port: int, ready: threading.Event, stop: threading.Event) -> None:
    """Background thread: open SSE conn, read until ": connected", then hold it open."""
    try:
        conn = _http.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/ai/insights/events/stream",
                     headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        # Read at least one chunk containing the connected comment.
        buf = b""
        while b": connected" not in buf and not stop.is_set():
            chunk = resp.read(64)
            if not chunk:
                break
            buf += chunk
        ready.set()
        # Hold connection open until told to stop.
        while not stop.is_set():
            try:
                _ = resp.read(64)  # may block or return on TERM
            except Exception:
                break
    except Exception:
        ready.set()


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    env = os.environ.copy()
    env.setdefault("GENOMEAI_WEB_SHUTDOWN_TIMEOUT", "10")

    cmd = [
        sys.executable, "-m", "uvicorn", "web_cabinet.app:app",
        "--host", "127.0.0.1", "--port", str(port),
        "--timeout-graceful-shutdown", env["GENOMEAI_WEB_SHUTDOWN_TIMEOUT"],
        "--log-level", "warning",
    ]
    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    iso = _dt.datetime.utcnow().isoformat() + "Z"
    try:
        deadline = time.monotonic() + 30.0
        if not _wait_for_port("127.0.0.1", port, deadline):
            proc.kill()
            ARTIFACT.write_text(f"FAIL elapsed=NA at {iso} reason=port_never_opened\n")
            return 1

        ready, stop = threading.Event(), threading.Event()
        t = threading.Thread(target=_read_sse_connected,
                             args=("127.0.0.1", port, ready, stop), daemon=True)
        t.start()
        if not ready.wait(timeout=10.0):
            proc.kill()
            stop.set()
            ARTIFACT.write_text(f"FAIL elapsed=NA at {iso} reason=sse_never_connected\n")
            return 1

        # Now the SSE generator is engaged and idle. Hit it with SIGTERM.
        t0 = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=HARD_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            elapsed = time.monotonic() - t0
            stop.set()
            ARTIFACT.write_text(
                f"FAIL elapsed={elapsed:.2f} at {iso} reason=process_did_not_exit\n"
            )
            return 1
        elapsed = time.monotonic() - t0
        stop.set()

        status = "OK" if elapsed < ACCEPTANCE_SEC else "FAIL"
        ARTIFACT.write_text(
            f"{status} elapsed={elapsed:.2f} at {iso} acceptance={ACCEPTANCE_SEC}s\n"
        )
        print(ARTIFACT.read_text().rstrip())
        return 0 if status == "OK" else 1
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/smoke_sse_shutdown.py
```

- [ ] **Step 3: Run the smoke**

Run:
```bash
.venv/bin/python scripts/smoke_sse_shutdown.py
```

Expected stdout: `OK elapsed=<X.XX> at <ISO> acceptance=3.0s` with `X.XX < 3.0`.
Expected exit code: 0.

If FAIL — read `artifacts/_ci/sse_shutdown_smoke.log` and investigate before continuing.

- [ ] **Step 4: Show artifact**

```bash
cat artifacts/_ci/sse_shutdown_smoke.log
```

- [ ] **Step 5: Commit script (artifact is gitignored per CLAUDE.md §11)**

```bash
git add scripts/smoke_sse_shutdown.py
git commit -m "$(cat <<'EOF'
test(sse): smoke proof that uvicorn exits in <3s with open SSE stream

Spawns real uvicorn, opens /api/ai/insights/events/stream, sends SIGTERM,
asserts process exits within 3s. Writes pass/fail to
artifacts/_ci/sse_shutdown_smoke.log.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Operations runbook note

**Files:**
- Modify: `docs/operations_runbook.md` (append)

- [ ] **Step 1: Append section**

Append to `docs/operations_runbook.md`:
```markdown

## Graceful shutdown timeout (uvicorn)

Backend launched via `python -m genomeai.app_launcher` passes
`--timeout-graceful-shutdown` to uvicorn. Default: `10` seconds. Override
via env:

    GENOMEAI_WEB_SHUTDOWN_TIMEOUT=20

App-level path: FastAPI lifespan shutdown handler calls
`web_cabinet.ai.endpoints.insights_stream.signal_shutdown()`, which wakes
all live SSE generators on `/api/ai/insights/events/stream`; fast-path
shutdown completes in <1 s. The uvicorn flag is a safety-net for any
streaming endpoint that does not (yet) observe the shutdown event.

If the backend ever appears to hang on SIGTERM:

1. Check `ss -tlnp | grep :8000` — listen socket should be gone.
2. Check `ss -anp | grep :8000` — count ESTABLISHED connections; non-zero
   means streaming clients are stuck.
3. Inspect logs (`/tmp/uvicorn.log` or `logs_dir/backend_uvicorn.log`).
4. Worst case — `kill -KILL` the process; investigate which streaming
   endpoint failed to honor the shutdown event.
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations_runbook.md
git commit -m "$(cat <<'EOF'
docs(ops): document GENOMEAI_WEB_SHUTDOWN_TIMEOUT + SSE shutdown protocol

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Regression gates

**Files:** none (verification only).

- [ ] **Step 1: Run unit-test gate for the new tests + adjacent SSE module**

Run:
```bash
.venv/bin/python -m pytest tests/test_insights_stream_shutdown.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 2: Run web smoke**

Run:
```bash
.venv/bin/python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json artifacts/_ci/web_smoke.json 2>&1 | tee artifacts/_ci/web_smoke.log | tail -20
```

Expected: exit 0, summary line "OK" / "PASSED" — confirm no regression in startup, login, or insights endpoint.

- [ ] **Step 3: Run pytest CI gate**

Run:
```bash
bash scripts/run_ci_gate.sh 2>&1 | tail -30
```

Expected: gate passes (exit 0). If failures unrelated to this change appear, capture them and decide whether to defer (do not silently swallow).

- [ ] **Step 4: Re-run smoke-proof for fresh artifact**

Run:
```bash
.venv/bin/python scripts/smoke_sse_shutdown.py && cat artifacts/_ci/sse_shutdown_smoke.log
```

Expected: `OK elapsed=<X.XX> ...` with `X.XX < 3.0`.

---

## Task 9: Iteration proof file

**Files:**
- Create: `docs/iterations/2026-05-12-sse-graceful-shutdown_execution_proof.md`

- [ ] **Step 1: Write proof file**

Create `docs/iterations/2026-05-12-sse-graceful-shutdown_execution_proof.md` with the following template, **filling in actual values from Task 8 runs**:
```markdown
# SSE Graceful Shutdown — Execution Proof

**Date:** 2026-05-12
**Spec:** docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md
**Plan:** docs/superpowers/plans/2026-05-12-sse-graceful-shutdown.md

## Scope
App-level shutdown event in insights_stream + uvicorn safety-net flag
in app_launcher. Closes class of bugs "long-lived streaming endpoint
blocks uvicorn graceful shutdown."

## Executed checks

### 1. Unit
`pytest -q tests/test_insights_stream_shutdown.py` → 4 passed (<paste tail>)

### 2. Web smoke
`python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean` →
artifacts/_ci/web_smoke.log → PASSED (<paste relevant summary>)

### 3. Pytest CI gate
`bash scripts/run_ci_gate.sh` → exit 0 (<paste tail>)

### 4. Smoke-proof
`python scripts/smoke_sse_shutdown.py`
Artifact: artifacts/_ci/sse_shutdown_smoke.log
Content: `<paste actual line, e.g. OK elapsed=0.18 at 2026-05-12T... acceptance=3.0s>`

## Net result
- Login outage class fixed: SSE-induced uvicorn hang on SIGTERM is no
  longer possible (app-level fast-path) or capped at 10 s (safety-net).
- No regressions observed in unit / web smoke / pytest gate.

## Honest status
proven — runtime smoke recorded, gates green.
```

- [ ] **Step 2: Commit proof**

```bash
git add docs/iterations/2026-05-12-sse-graceful-shutdown_execution_proof.md
git commit -m "$(cat <<'EOF'
docs(iter): execution proof for SSE graceful shutdown fix

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Final summary to user**

Report:
- Commits added (list `git log --oneline -7`).
- Proof artifact path + actual elapsed time.
- Status: `proven` (runtime smoke + gates).
- Open follow-ups: client-disconnect detection (out of scope; separate task).

---

## Self-Review (executed before saving)

**Spec coverage:**
- App-level shutdown event → Task 3. ✓
- signal_shutdown() public + idempotent → Task 3 + tests in Task 2. ✓
- _event_generator races queue.get() vs _shutdown_event → Task 3. ✓
- Hook in lifespan _shutdown() → Task 4. ✓
- uvicorn --timeout-graceful-shutdown via env → Task 5. ✓
- Unit test → Task 2 + Task 3 step 3. ✓
- Smoke proof script + artifact → Task 6 + Task 8 step 4. ✓
- Runbook doc → Task 7. ✓
- Files list in spec — all touched in plan. ✓
- Acceptance criteria (pytest, smoke <3 s, web_smoke clean, CI gate clean) → Task 8. ✓
- Out of scope honored — no `ask_farm.py` or `request.is_disconnected()` changes. ✓

**Placeholder scan:** No TBD / TODO / "handle edge cases". Every code step has exact code. Every command has expected output. ✓

**Type / name consistency:**
- `_shutdown_event`, `signal_shutdown`, `_event_generator`, `_subscribers`, `broadcast_insights_event` — used identically in Task 2 (tests), Task 3 (impl), Task 4 (wiring). ✓
- env var `GENOMEAI_WEB_SHUTDOWN_TIMEOUT` — same in Task 5, Task 6 script, Task 7 runbook. ✓
- Artifact path `artifacts/_ci/sse_shutdown_smoke.log` — same in spec, Task 6, Task 8, Task 9. ✓
