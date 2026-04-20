from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from core.audit import load_audit_retention_config
from core.config import ConfigValidationError, validate_startup_config_bundle
from core.security import SecurityMatrixConfigError, load_permission_matrix
from web_cabinet import app as web_app
from web_cabinet.jobs_v2 import load_job_runner_config


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_t15_11_job_runner_config_validation_is_human_readable(tmp_path: Path) -> None:
    _write(tmp_path / "configs" / "jobs" / "runner_v2.yaml", "max_attempts_default: bad\n")

    with pytest.raises(ConfigValidationError) as exc:
        load_job_runner_config(tmp_path)

    message = str(exc.value)
    assert "runner_v2" in message
    assert "max_attempts_default" in message
    assert "runner_v2.yaml" in message


def test_t15_11_permission_matrix_validation_uses_core_loader_message(tmp_path: Path) -> None:
    _write(tmp_path / "configs" / "security" / "permission_matrix_v1.yaml", "version: 1\nactions: []\n")

    with pytest.raises(SecurityMatrixConfigError) as exc:
        load_permission_matrix(tmp_path)

    message = str(exc.value)
    assert "permission_matrix_v1" in message
    assert "actions" in message
    assert "permission_matrix_v1.yaml" in message


def test_t15_11_audit_retention_validation_is_human_readable(tmp_path: Path) -> None:
    _write(tmp_path / "configs" / "security" / "audit_retention_v1.yaml", "archive_after_days: 0\n")

    with pytest.raises(ValueError) as exc:
        load_audit_retention_config(tmp_path)

    message = str(exc.value)
    assert "audit_retention_config_invalid" in message
    assert "archive_after_days" in message
    assert "audit_retention_v1.yaml" in message


def test_t15_11_validate_startup_config_bundle_loads_all_core_configs(tmp_path: Path) -> None:
    _write(
        tmp_path / "configs" / "security" / "permission_matrix_v1.yaml",
        "version: 1\nactions:\n  run:\n    permissions: [pipeline.run]\n",
    )
    _write(tmp_path / "configs" / "security" / "audit_retention_v1.yaml", "enabled: true\narchive_after_days: 30\n")
    _write(tmp_path / "configs" / "jobs" / "runner_v2.yaml", "queue_name_default: ops\nmax_attempts_default: 3\n")

    summary = validate_startup_config_bundle(tmp_path)

    assert summary["permission_matrix_version"] == 1
    assert summary["audit_retention_version"] == 1
    assert summary["job_runner_queue"] == "ops"
    assert summary["job_runner_max_attempts"] == 3


def test_t15_11_web_startup_calls_startup_config_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []

    monkeypatch.setattr(web_app, "validate_runtime_config", lambda settings: {"profile": "dev"})
    monkeypatch.setattr(web_app, "validate_startup_config_bundle", lambda project_root: calls.append(Path(project_root)) or {"ok": True})
    monkeypatch.setattr(web_app, "settings", SimpleNamespace(project_root=tmp_path, db_path=tmp_path / "web.db"))
    monkeypatch.setattr(web_app, "hash_password", lambda value: value)
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")

    class _Conn:
        def close(self) -> None:
            return None

    fake_db = ModuleType("web_cabinet.db")
    fake_db.connect = lambda path: _Conn()
    fake_playbooks = ModuleType("web_cabinet.playbooks_v1")
    fake_playbooks.ensure_default_playbooks = lambda conn, tenant_id="default": None

    monkeypatch.setitem(sys.modules, "web_cabinet.db", fake_db)
    monkeypatch.setitem(sys.modules, "web_cabinet.playbooks_v1", fake_playbooks)
    monkeypatch.setattr(web_app, "init_db", lambda conn: None)
    monkeypatch.setattr(web_app, "ensure_default_users", lambda conn, hash_password_fn: None)
    monkeypatch.setattr(web_app, "ensure_default_users_v2", lambda conn, tenant_id, hash_password_fn: None)

    web_app._startup()

    assert calls == [tmp_path]
