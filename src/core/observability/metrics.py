from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class JobMetric:
    kind: str
    total: int = 0
    ok: int = 0
    failed: int = 0
    last_status: str | None = None
    last_exit_code: int | None = None
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_duration_sec: float | None = None
    p95_duration_sec: float | None = None


@dataclass
class RequestMetric:
    route_key: str
    total: int = 0
    ok: int = 0
    failed: int = 0
    in_flight: int = 0
    last_status_code: int | None = None
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_duration_sec: float | None = None
    p95_duration_sec: float | None = None


@dataclass
class CommandMetric:
    command: str
    total: int = 0
    ok: int = 0
    failed: int = 0
    last_status: str | None = None
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_duration_sec: float | None = None
    p95_duration_sec: float | None = None


_lock = threading.Lock()
_start_time = time.time()
_job_by_kind: dict[str, JobMetric] = {}
_job_durations: dict[str, list[float]] = {}
_request_by_route: dict[str, RequestMetric] = {}
_request_durations: dict[str, list[float]] = {}
_command_by_name: dict[str, CommandMetric] = {}
_command_durations: dict[str, list[float]] = {}



def _bounded_append(store: dict[str, list[float]], key: str, value: float, *, limit: int = 200) -> list[float]:
    hist = store.setdefault(key, [])
    hist.append(float(value))
    if len(hist) > limit:
        del hist[: len(hist) - limit]
    return hist



def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    idx = int(round(0.95 * (len(vs) - 1)))
    return float(vs[idx])



def record_job_start(kind: str) -> None:
    now = time.time()
    with _lock:
        metric = _job_by_kind.setdefault(str(kind or "job"), JobMetric(kind=str(kind or "job")))
        metric.last_started_at = now



def record_job_finish(kind: str, *, status: str, exit_code: int, duration_sec: float) -> None:
    now = time.time()
    key = str(kind or "job")
    with _lock:
        metric = _job_by_kind.setdefault(key, JobMetric(kind=key))
        metric.total += 1
        if str(status or "") == "done":
            metric.ok += 1
        else:
            metric.failed += 1
        metric.last_status = str(status or "") or None
        metric.last_exit_code = int(exit_code)
        metric.last_finished_at = now
        metric.last_duration_sec = float(duration_sec)
        metric.p95_duration_sec = _p95(_bounded_append(_job_durations, key, duration_sec))



def record_request_start(*, method: str, path: str) -> None:
    now = time.time()
    route_key = f"{str(method or 'GET').upper()} {str(path or '/')}"
    with _lock:
        metric = _request_by_route.setdefault(route_key, RequestMetric(route_key=route_key))
        metric.in_flight += 1
        metric.last_started_at = now



def record_request_finish(*, method: str, path: str, status_code: int, duration_sec: float) -> None:
    now = time.time()
    route_key = f"{str(method or 'GET').upper()} {str(path or '/')}"
    with _lock:
        metric = _request_by_route.setdefault(route_key, RequestMetric(route_key=route_key))
        metric.total += 1
        metric.in_flight = max(0, metric.in_flight - 1)
        if int(status_code) < 500:
            metric.ok += 1
        else:
            metric.failed += 1
        metric.last_status_code = int(status_code)
        metric.last_finished_at = now
        metric.last_duration_sec = float(duration_sec)
        metric.p95_duration_sec = _p95(_bounded_append(_request_durations, route_key, duration_sec))



def record_command_start(command: str) -> None:
    now = time.time()
    key = str(command or "cli")
    with _lock:
        metric = _command_by_name.setdefault(key, CommandMetric(command=key))
        metric.last_started_at = now



def record_command_finish(command: str, *, status: str, duration_sec: float) -> None:
    now = time.time()
    key = str(command or "cli")
    with _lock:
        metric = _command_by_name.setdefault(key, CommandMetric(command=key))
        metric.total += 1
        if str(status or "") == "ok":
            metric.ok += 1
        else:
            metric.failed += 1
        metric.last_status = str(status or "") or None
        metric.last_finished_at = now
        metric.last_duration_sec = float(duration_sec)
        metric.p95_duration_sec = _p95(_bounded_append(_command_durations, key, duration_sec))



def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "uptime_sec": float(time.time() - _start_time),
            "jobs": {key: asdict(metric) for key, metric in sorted(_job_by_kind.items())},
            "requests": {
                "total": int(sum(metric.total for metric in _request_by_route.values())),
                "in_flight": int(sum(metric.in_flight for metric in _request_by_route.values())),
                "routes": {key: asdict(metric) for key, metric in sorted(_request_by_route.items())},
            },
            "commands": {key: asdict(metric) for key, metric in sorted(_command_by_name.items())},
        }



def reset_metrics() -> None:
    global _start_time
    with _lock:
        _start_time = time.time()
        _job_by_kind.clear()
        _job_durations.clear()
        _request_by_route.clear()
        _request_durations.clear()
        _command_by_name.clear()
        _command_durations.clear()


__all__ = [
    "CommandMetric",
    "JobMetric",
    "RequestMetric",
    "record_command_finish",
    "record_command_start",
    "record_job_finish",
    "record_job_start",
    "record_request_finish",
    "record_request_start",
    "reset_metrics",
    "snapshot",
]
