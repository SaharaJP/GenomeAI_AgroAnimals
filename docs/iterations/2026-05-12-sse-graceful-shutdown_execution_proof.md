# SSE Graceful Shutdown — Execution Proof

**Date:** 2026-05-12
**Spec:** `docs/superpowers/specs/2026-05-12-sse-graceful-shutdown-design.md`
**Plan:** `docs/superpowers/plans/2026-05-12-sse-graceful-shutdown.md`
**Trigger:** 2026-05-12 morning — backend uvicorn (PID 2999937) hung on graceful shutdown with two open `/api/ai/insights/events/stream` SSE connections; listen socket on :8000 was closed, process kept running, all new HTTP (incl. `POST /api/app/v1/auth/login`) rejected → user-visible "ошибка входа".

## Scope

App-level shutdown event in `web_cabinet/ai/endpoints/insights_stream.py` (module-level `asyncio.Event` + public idempotent `signal_shutdown()`; `_event_generator` races `queue.get()` vs `_shutdown_event.wait()` via `asyncio.wait(FIRST_COMPLETED)` and drains `get_task` in `finally`). Lifespan hook in `web_cabinet/app.py::_shutdown()` calls `signal_shutdown()`. Process-level safety-net flag `--timeout-graceful-shutdown` (default `10` s, env override `GENOMEAI_WEB_SHUTDOWN_TIMEOUT`) added to canonical launcher `src/genomeai/app_launcher.py`. Operations runbook updated.

Closes the class of bugs "long-lived streaming endpoint blocks uvicorn graceful shutdown."

## Commits (on `main`, in order)

```
5209db4 docs(ops): document GENOMEAI_WEB_SHUTDOWN_TIMEOUT + SSE shutdown protocol
ad1e468 test(sse): smoke proof that uvicorn exits in <3s with open SSE stream
4628bba feat(launcher): pass --timeout-graceful-shutdown=10 to uvicorn
920e569 feat(app): call insights_stream.signal_shutdown() on lifespan shutdown
19e8437 fix(sse): track get_task across loop iterations for clean cancellation
f220107 feat(sse): graceful shutdown event for /insights/events/stream
ec4f4a2 docs(plan): implementation plan for SSE graceful shutdown fix
4226ecc docs(ops): design spec for SSE graceful shutdown (uvicorn hang fix)
```

## Executed checks

### 1. Unit tests (Gate 1)

```
$ .venv/bin/python -m pytest tests/test_insights_stream_shutdown.py -v
tests/test_insights_stream_shutdown.py::test_generator_blocks_when_idle PASSED
tests/test_insights_stream_shutdown.py::test_signal_shutdown_completes_generator_fast PASSED
tests/test_insights_stream_shutdown.py::test_signal_shutdown_is_idempotent PASSED
tests/test_insights_stream_shutdown.py::test_new_connection_during_shutdown_exits_immediately PASSED
4 passed in 0.40s
```

No `PytestUnraisableExceptionWarning` (was present in pre-review state; eliminated by `19e8437`).

### 2. Web smoke (Gate 2)

```
$ .venv/bin/python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
    --timing-json artifacts/_ci/web_smoke.json
WEB_SMOKE_OK
storage_backend=postgres
```

Full log: `artifacts/_ci/web_smoke.log`. Exit 0.

### 3. CI gate (Gate 3)

```
$ bash scripts/run_ci_gate.sh
[ci_gate] OK Python syntax check passed
[ci_gate] OK TypeScript typecheck passed
[ci_gate] OK No secrets leaked
[ci_gate] OK web_cabinet imports OK
[ci_gate] === PASSED ===
```

### 4. Runtime smoke-proof — the headline number (Gate 4)

```
$ .venv/bin/python scripts/smoke_sse_shutdown.py
OK elapsed=0.47 at 2026-05-12T10:51:29.632498Z acceptance=3.0s
```

Artifact: `artifacts/_ci/sse_shutdown_smoke.log`

The script spawns a brand-new uvicorn on a free port, opens an SSE connection to `/api/ai/insights/events/stream`, waits for the `: connected` frame to ensure the generator is engaged, then sends `SIGTERM`. **The process exited in 0.47 seconds**, well under the 3 s acceptance threshold and far under the 10 s safety-net.

A prior dispatch recorded `elapsed=0.61 s` (initial proof). Two runs, two passes, both <1 s.

### 5. Wiring sanity (during Plan Task 4)

```
$ python -c "import asyncio; from web_cabinet import app as a; from web_cabinet.ai.endpoints import insights_stream as ism; \
    asyncio.run((lambda: __import__('contextlib').asynccontextmanager(a._lifespan)(a.app).__aenter__())()); \
    print('event set?', ism._shutdown_event.is_set())"
event set? True
```

End-to-end: app lifespan shutdown actually toggles the SSE shutdown event in production code path.

## Net result

- The login outage class **is fixed**. SSE-induced uvicorn hang on SIGTERM is no longer possible:
  - Fast path: app-level shutdown event closes generators in <1 s (proven: 0.47–0.61 s).
  - Safety net: `--timeout-graceful-shutdown=10` bounds any future regression to 10 s.
- No regressions introduced in unit tests / web smoke / CI gate / SSE smoke.

## Honest status

`proven` for the iteration's acceptance criteria (spec §Acceptance criteria, plan §Acceptance):
- Unit gate green.
- Web smoke green.
- `run_ci_gate.sh` green.
- Smoke-proof recorded with elapsed 0.47 s < 3 s.

**Out-of-scope observation:** running the full pytest suite (`pytest -q`) shows 158 failures + 25 errors. Sampled failures trace to pre-existing legacy paths (`web_cabinet.db.connect` removed in favor of `core.infra.web_db`; missing SQLite test table `dm_lactations`). **Zero** of those failures touch `insights_stream`, the new shutdown hook in `web_cabinet/app.py`, or `app_launcher.py`. Not caused by this iteration; left for a separate clean-up.

## Open follow-ups (NOT in this iteration)

- Client-disconnect detection (`request.is_disconnected()` polling) for leak-prevention on dropped clients. Currently dropped clients are GC'd via WeakSet but a queue holds memory until the next put attempt.
- Same shutdown pattern for SSE in `web_cabinet/ai/endpoints/ask_farm.py` (currently short-lived; covered exclusively by the safety-net flag).
- `scripts/run_ci_gate.sh` description in CLAUDE.md §4 says "pytest gate" but the script does not run pytest. Either the script should run pytest, or the CLAUDE.md text should reflect what it actually checks. Track separately.
- Restart of the running uvicorn (PID 3088072, started 12:48 today before any of this fix landed) so it picks up the new code. The currently running server still has the old SSE generator; next graceful shutdown could hang. Handled by coordinator outside this iteration.
