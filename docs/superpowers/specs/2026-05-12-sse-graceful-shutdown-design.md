---
title: "SSE Graceful Shutdown — uvicorn hang fix (Design)"
date: 2026-05-12
author: server Claude (T34 ops/supportability)
trigger_incident: 2026-05-12 morning — backend uvicorn (PID 2999937) hung on graceful shutdown with two open `/api/ai/insights/events/stream` SSE connections; listen socket on :8000 closed, process kept running, all new HTTP (including `POST /api/app/v1/auth/login`) refused → user-visible "ошибка входа".
status: approved-for-planning
---

# SSE Graceful Shutdown — Design Specification

## Цель

При получении SIGTERM uvicorn должен завершаться **за секунды**, а не висеть бесконечно на долгоживущих SSE-стримах. Лечим первопричину сегодняшнего инцидента входа и закрываем класс багов «один streaming endpoint вешает весь процесс на shutdown».

## Acceptance criteria

- Unit-тест: `_event_generator`, запущенный как asyncio.Task, при пустой очереди не завершается за 50 мс; после вызова `signal_shutdown()` завершается за <200 мс; `_subscribers` пуст.
- Smoke-скрипт: uvicorn с открытым SSE-коннектом на `/api/ai/insights/events/stream` после `SIGTERM` главному процессу выходит за <3 с; артефакт `artifacts/_ci/sse_shutdown_smoke.log` фиксирует время.
- Зелёный `pytest -q tests/test_insights_stream_shutdown.py`.
- `bash scripts/run_ci_gate.sh` — без регрессий.
- `python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean` — без регрессий.
- В отсутствие любого app-level бага в SSE генераторах: uvicorn принудительно завершается через `--timeout-graceful-shutdown=10` (safety-net наблюдается в smoke-скрипте отдельным тестом).

## Scope

### Включено
- Application-level shutdown event в `web_cabinet/ai/endpoints/insights_stream.py`.
- Хук в существующем `_shutdown()` (web_cabinet/app.py) для трансляции shutdown в SSE-модуль.
- uvicorn-флаг `--timeout-graceful-shutdown` в каноническом запуске (`src/genomeai/app_launcher.py`) с управлением через env `GENOMEAI_WEB_SHUTDOWN_TIMEOUT` (default `10`).
- Unit-тест на shutdown event.
- Smoke-скрипт с реальным uvicorn + SIGTERM.
- Заметка в `docs/operations_runbook.md` про env-переменную.

### Не включено (отдельные задачи)
- Детекция оборвавшихся клиентов (`request.is_disconnected()`) и leak-prevention.
- Аналогичная обработка для SSE в `web_cabinet/ai/endpoints/ask_farm.py`: эти стримы короткоживущие (один Q&A — закрывается); покрываются исключительно safety-net'ом.
- Изменения процессного supervision'а (systemd unit и т.п.).

## Архитектура

```
SIGTERM
  → uvicorn (closes listen socket)
    → FastAPI lifespan shutdown phase
      → web_cabinet/app.py::_shutdown()
        ├─ existing: worker.stop(), stop_cron(...) x3
        └─ NEW: insights_stream.signal_shutdown()
              ↓ sets module-level asyncio.Event
        all live _event_generator() coroutines:
          wait race(queue.get(), _shutdown_event.wait()) wakes up
          → break loop → finally: _subscribers.discard(queue)
      → uvicorn: no active tasks → process exits (~ms)

  Safety-net (independent layer): if any streaming task hangs,
  uvicorn `--timeout-graceful-shutdown=10` cancels everything after 10s.
```

**Ключевое решение:** app-level fix через `asyncio.Event` — потому что uvicorn graceful shutdown **не отменяет** активные streaming-задачи, он их **ожидает**. Только наше явное сигнализирование завершает их корректно.

## Компонент 1: shutdown event в insights_stream.py

Файл: `web_cabinet/ai/endpoints/insights_stream.py`.

### Добавляем
```python
# Module-level shutdown signal (set by FastAPI lifespan shutdown handler).
_shutdown_event: asyncio.Event = asyncio.Event()


def signal_shutdown() -> None:
    """Сигнализирует всем активным _event_generator корутинам выйти.

    Идемпотентен. Безопасно вызывать из FastAPI lifespan shutdown handler
    (тот же event loop) и из threadpool callbacks (asyncio.Event.set() — thread-safe).
    """
    _shutdown_event.set()
```

### Меняем `_event_generator`
Текущая реализация (web_cabinet/ai/endpoints/insights_stream.py:42-58):

```python
async def _event_generator(queue):
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
        _subscribers.discard(queue)
```

Новая реализация:

```python
async def _event_generator(queue):
    yield ": connected\n\n"
    # Если shutdown уже идёт к моменту подключения — сразу выходим.
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
                # timeout → heartbeat
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
```

**Важно:**
- `_shutdown_event` создаётся при импорте модуля; используется один и тот же event loop, что и у FastAPI (lifespan вызывается в основном loop).
- `shutdown_task` создаётся **один раз на коннект** (а не на итерацию), иначе пересоздание `wait()` бесконечно плодит таски.
- `get_task` пересоздаётся каждую итерацию (что и было неявно в `asyncio.wait_for`).
- Все ветки финализации отменяют `get_task` и `shutdown_task`, чтобы не было «task was destroyed but it is pending» warning.

## Компонент 2: вызов signal_shutdown() из lifespan

Файл: `web_cabinet/app.py`, функция `_shutdown()` (line ~606). Существующий хук уже регистрируется через `_lifespan` context manager (line 633-639), новая регистрация не нужна.

В конец `_shutdown()` добавляем:
```python
try:
    from web_cabinet.ai.endpoints.insights_stream import signal_shutdown as _sse_signal_shutdown
    _sse_signal_shutdown()
except Exception:
    pass
```

Pattern (try/except, lazy import) идентичен соседним блокам остановки cron'ов — для консистентности и устойчивости к refactor'у.

## Компонент 3: uvicorn safety-net

Файл: `src/genomeai/app_launcher.py`, секция `cmd_backend` (line 86-95).

```python
_shutdown_timeout = os.environ.get("GENOMEAI_WEB_SHUTDOWN_TIMEOUT", "10")
cmd_backend = [
    sys.executable,
    "-m",
    "uvicorn",
    "web_cabinet.app:app",
    "--host", args.host,
    "--port", str(args.backend_port),
    "--timeout-graceful-shutdown", _shutdown_timeout,
]
```

Default `10` секунд — достаточно для корректного fast-path (app-level shutdown даёт <1 с), но не настолько долго, чтобы blocking restart был болезненным.

## Тесты

### Unit: `tests/test_insights_stream_shutdown.py`

```python
import asyncio
import pytest
from web_cabinet.ai.endpoints import insights_stream as ism


@pytest.mark.asyncio
async def test_generator_does_not_complete_when_idle():
    # Setup: reset event between tests (the module-level event is shared state)
    ism._shutdown_event.clear()
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    ism._subscribers.add(q)
    gen = ism._event_generator(q)

    # Pull "connected" line — generator now blocks on queue.get().
    first = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
    assert first.startswith(": connected")

    # Should NOT yield more within 50 ms while idle.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(gen.__anext__(), timeout=0.05)

    # Cleanup
    await gen.aclose()


@pytest.mark.asyncio
async def test_signal_shutdown_completes_generator_fast():
    ism._shutdown_event.clear()
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    ism._subscribers.add(q)
    gen = ism._event_generator(q)
    # Consume "connected"
    await asyncio.wait_for(gen.__anext__(), timeout=0.5)

    ism.signal_shutdown()

    # Expect StopAsyncIteration within 200 ms.
    t0 = asyncio.get_event_loop().time()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=0.2)
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed < 0.2

    # Subscriber должен быть удалён.
    assert q not in list(ism._subscribers)
```

Tests располагаются в `tests/test_insights_stream_shutdown.py`. Используем `pytest-asyncio` (уже в зависимостях, см. соседние async-тесты).

### Smoke / proof: `scripts/smoke_sse_shutdown.py`

Standalone Python-скрипт, исполняемый отдельно (не в pytest):

1. `subprocess.Popen` поднимает uvicorn с `--timeout-graceful-shutdown=10` на свободном порту.
2. Дожидается listen-сокета (poll `ss` или попытка connect).
3. Открывает SSE-коннект `urllib` (или `httpx`) в фоне; читает `": connected"`.
4. `os.kill(proc.pid, signal.SIGTERM)`; засекает время.
5. `proc.wait(timeout=15)` — фиксирует elapsed.
6. Acceptance: `elapsed < 3.0` (app-level fast-path).
7. Записывает строку в `artifacts/_ci/sse_shutdown_smoke.log` формата `OK elapsed=<sec> at <iso-ts>`.
8. Дополнительный sub-test: повторить, но **симулировав** app-level breakage (например, monkey-patched `signal_shutdown` через env-флаг или через временную правку). Acceptance: `elapsed < 11.0` (safety-net хитит в 10 с). Если симуляция через env слишком инвазивна для скоупа — этот sub-test делаем как documented manual check, не часть скрипта.

Артефакт коммитится в proof-файле итерации.

## Обработка ошибок и edge cases

- **Повторный SIGTERM** во время уже идущего shutdown — `signal_shutdown()` идемпотентен.
- **Новый SSE-коннект во время shutdown** — `_event_generator` сразу видит `_shutdown_event.is_set()` и выходит, корректно почистив subscriber.
- **`broadcast_insights_event` во время shutdown** — функция вызывается из threadpool callback APScheduler'а; даже если он попытается `put_nowait` в очередь, generator уже завершается, queue будет собрана GC. Не требует изменений.
- **Тестовая изоляция** — `_shutdown_event` модуль-level; в unit-тестах явно `_shutdown_event.clear()` в каждом тесте (или фикстура).

## Риски и допущения

- Допущение: FastAPI lifespan shutdown handler выполняется в основном asyncio loop приложения — следовательно, `_shutdown_event.set()` виден ожидающим в этом же loop корутинам. Проверено документацией FastAPI + ручным smoke-скриптом.
- Риск: при тяжёлом GC или большом числе подписчиков пробуждение всех generator'ов может занять >50 мс. Smoke-скрипт измеряет реальный wall-time; если будет >3 с в реальном тесте — это **сам по себе** проваленный test, и нужно разбираться.
- Риск: `--timeout-graceful-shutdown` доступен в uvicorn 0.18+. Текущая версия — проверить в `pip show uvicorn` (план реализации).

## Файлы

- M: `web_cabinet/ai/endpoints/insights_stream.py`
- M: `web_cabinet/app.py` (один блок в `_shutdown()`)
- M: `src/genomeai/app_launcher.py` (флаг + env)
- M: `docs/operations_runbook.md` (заметка)
- A: `tests/test_insights_stream_shutdown.py`
- A: `scripts/smoke_sse_shutdown.py`
- A: `artifacts/_ci/sse_shutdown_smoke.log` (proof artifact, генерируется в момент proof-прогона)

## Out of scope

- Client-disconnect detection / leak prevention.
- SSE в `ask_farm.py`.
- Замена `--timeout-graceful-shutdown` на полностью кастомный shutdown-протокол (например, `SIGUSR1`-инициация app-level shutdown без закрытия listener).
