from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastapi.testclient import TestClient


def _reload_app_module(monkeypatch, tmp_path: Path, *, disable_worker: bool):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GENOMEAI_WEB_SECRET", "test-secret")
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1" if disable_worker else "0")

    import web_cabinet.app as appmod

    return importlib.reload(appmod)


def test_t16_02_app_uses_lifespan_handlers_not_on_event(monkeypatch, tmp_path: Path) -> None:
    appmod = _reload_app_module(monkeypatch, tmp_path, disable_worker=True)

    assert appmod.app.router.on_startup == []
    assert appmod.app.router.on_shutdown == []
    assert appmod.app.router.lifespan_context is not None


def test_t16_02_lifespan_preserves_startup_order_and_stops_worker(monkeypatch, tmp_path: Path) -> None:
    appmod = _reload_app_module(monkeypatch, tmp_path, disable_worker=False)
    calls: list[str] = []

    monkeypatch.setattr(appmod, "settings", SimpleNamespace(project_root=tmp_path, db_path=tmp_path / "web.db"))
    monkeypatch.setattr(appmod, "validate_runtime_config", lambda settings: calls.append("validate_runtime_config") or {"profile": "dev"})
    monkeypatch.setattr(
        appmod,
        "validate_startup_config_bundle",
        lambda project_root: calls.append(f"validate_startup_config_bundle:{Path(project_root).name}") or {"ok": True},
    )
    monkeypatch.setattr(appmod, "hash_password", lambda value: value)
    monkeypatch.setattr(appmod, "init_db", lambda conn: calls.append("init_db"))
    monkeypatch.setattr(appmod, "ensure_default_users", lambda conn, hash_password_fn: calls.append("ensure_default_users"))
    monkeypatch.setattr(
        appmod,
        "ensure_default_users_v2",
        lambda conn, tenant_id, hash_password_fn: calls.append(f"ensure_default_users_v2:{tenant_id}"),
    )

    class _Conn:
        def close(self) -> None:
            calls.append("conn.close")

    fake_db = ModuleType("web_cabinet.db")
    fake_db.connect = lambda path: calls.append(f"connect:{Path(path).name}") or _Conn()

    fake_playbooks = ModuleType("web_cabinet.playbooks_v1")
    fake_playbooks.ensure_default_playbooks = lambda conn, tenant_id="default": calls.append(f"ensure_default_playbooks:{tenant_id}")

    monkeypatch.setitem(sys.modules, "web_cabinet.db", fake_db)
    monkeypatch.setitem(sys.modules, "web_cabinet.playbooks_v1", fake_playbooks)

    class _Worker:
        _thread = None

        def start(self) -> None:
            calls.append("worker.start")

        def stop(self) -> None:
            calls.append("worker.stop")

    monkeypatch.setattr(appmod, "worker", _Worker())

    with TestClient(appmod.app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.text.strip() == "ok"

    assert calls == [
        "validate_runtime_config",
        f"validate_startup_config_bundle:{tmp_path.name}",
        "connect:web.db",
        "init_db",
        "ensure_default_users",
        "ensure_default_users_v2:default",
        "ensure_default_playbooks:default",
        "conn.close",
        "worker.start",
        "worker.stop",
    ]


def test_t16_02_job_worker_can_restart_after_stop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(Path(__file__).resolve().parents[1]))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))

    from web_cabinet.worker import JobWorker

    worker = JobWorker()
    calls: list[str] = []

    def fake_loop() -> None:
        calls.append("loop")

    monkeypatch.setattr(worker, "_loop", fake_loop)

    worker.start()
    worker.stop()
    worker.start()
    worker.stop()

    assert calls == ["loop", "loop"]
    assert worker._thread is None
