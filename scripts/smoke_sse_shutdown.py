#!/usr/bin/env python3
"""Smoke-proof: uvicorn must exit within 3s of SIGTERM with an open SSE stream.

Spawns uvicorn on a free port, opens an SSE connection to
/api/ai/insights/events/stream, reads the ": connected" frame to ensure the
generator is engaged, then sends SIGTERM to the uvicorn process and measures
wall-time until process exit.

Writes a single-line result to artifacts/_ci/sse_shutdown_smoke.log:
  OK   elapsed=<sec> at <iso-ts>     - pass
  FAIL elapsed=<sec> at <iso-ts> ... - fail (also exit code 1)
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
        buf = b""
        while b": connected" not in buf and not stop.is_set():
            chunk = resp.read(64)
            if not chunk:
                break
            buf += chunk
        ready.set()
        while not stop.is_set():
            try:
                _ = resp.read(64)
            except Exception:
                break
    except Exception:
        ready.set()


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    env = os.environ.copy()
    # Force a high safety-net so a fast exit is unambiguously the app-level
    # fast-path, not the uvicorn graceful-shutdown timeout firing under the
    # ACCEPTANCE_SEC threshold. Must remain >> ACCEPTANCE_SEC.
    env["GENOMEAI_WEB_SHUTDOWN_TIMEOUT"] = "30"

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
