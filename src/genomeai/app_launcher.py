from __future__ import annotations

"""Launcher for the local full-app experience.

Backend remains the Python-served process. The primary product UI is the standalone web
frontend (React/Next.js), which is started separately in production/dev workflows.
This launcher therefore starts FastAPI backend services and optionally opens the web URL,
but does not launch any legacy embedded UI layer.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def _env_with_defaults(artifacts_root: Path, web_db_path: Path, openai_api_key: str | None) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("GENOMEAI_ARTIFACTS", str(artifacts_root))
    env.setdefault("GENOMEAI_WEB_DB", str(web_db_path))
    if openai_api_key:
        env["OPENAI_API_KEY"] = openai_api_key
    return env


def _popen(cmd: list[str], env: dict[str, str], cwd: Path, log_path: Path | None) -> subprocess.Popen:
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(log_path, "ab", buffering=0)
        return subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=f, stderr=subprocess.STDOUT)
    return subprocess.Popen(cmd, cwd=str(cwd), env=env)


def _terminate(p: subprocess.Popen, timeout_sec: int = 10) -> None:
    if p.poll() is not None:
        return
    try:
        p.terminate()
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            if p.poll() is not None:
                return
            time.sleep(0.2)
        p.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genomeai-agroanimals", description="Launch GenomeAI AgroAnimals locally (web frontend primary, FastAPI backend)")
    p.add_argument("--no-ui", action="store_true", help="Do not open the primary web frontend URL in browser")
    p.add_argument("--no-backend", action="store_true", help="Do not start FastAPI backend")
    p.add_argument("--ui-port", type=int, default=int(os.environ.get("GENOMEAI_WEB_UI_PORT", "3000")))
    p.add_argument("--backend-port", type=int, default=int(os.environ.get("GENOMEAI_WEB_PORT", "8000")))
    p.add_argument("--host", default=os.environ.get("GENOMEAI_HOST", "127.0.0.1"))
    p.add_argument("--artifacts", default=os.environ.get("GENOMEAI_ARTIFACTS", "artifacts"))
    p.add_argument("--web-db", default=os.environ.get("GENOMEAI_WEB_DB", "web_cabinet/storage/web.db"))
    p.add_argument("--open-browser", action="store_true", help="Open browser after start (prefers standalone web frontend)")
    p.add_argument("--dry-run", action="store_true", help="Print commands and exit")
    p.add_argument("--logs", default=os.environ.get("GENOMEAI_LOGS_DIR", "runtime/logs"))
    p.add_argument("--openai-api-key", default=os.environ.get("OPENAI_API_KEY"), help="Optional: enable LLM reports")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    artifacts_root = Path(args.artifacts).expanduser().resolve()
    web_db_path = Path(args.web_db).expanduser().resolve()
    logs_dir = Path(args.logs).expanduser().resolve()

    ui_url = f"http://{args.host}:{args.ui_port}"
    backend_url = f"http://{args.host}:{args.backend_port}"
    web_public_url = os.environ.get("GENOMEAI_WEB_PUBLIC_URL", ui_url)

    env = _env_with_defaults(artifacts_root=artifacts_root, web_db_path=web_db_path, openai_api_key=args.openai_api_key)

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

    if args.dry_run:
        print("DRY_RUN")
        print("PRIMARY_ENTRY:", "web_frontend")
        print("WEB_URL:", web_public_url)
        if not args.no_backend:
            print("BACKEND:", " ".join(cmd_backend))
        return 0

    procs: list[subprocess.Popen] = []
    try:
        if not args.no_backend:
            procs.append(_popen(cmd_backend, env, repo_root, logs_dir / "backend_uvicorn.log"))
        if args.open_browser and not args.no_ui:
            time.sleep(1.0)
            try:
                webbrowser.open(web_public_url)
            except Exception:
                pass
        if not procs:
            return 0
        while True:
            time.sleep(0.5)
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    return int(rc)
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            _terminate(p)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
