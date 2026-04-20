from __future__ import annotations

from pathlib import Path

import pytest

from core.infra.runtime_storage import (
    resolve_runtime_storage_settings,
    runtime_storage_diagnostics,
    validate_runtime_storage_settings,
    validate_sqlite_compat_access,
    RuntimeStorageConfigError,
)
from web_cabinet.deploy_guard import DeployConfigError, validate_runtime_config
from core.infra.web_db import get_settings


def test_t34_01_doc_and_alembic_baseline_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "postgres_cutover_foundation.md").exists()
    assert (root / "alembic.ini").exists()
    assert (root / "src" / "core" / "migrations" / "alembic" / "env.py").exists()
    assert (root / "src" / "core" / "migrations" / "alembic" / "versions" / "README.md").exists()


def test_t34_01_dev_profile_uses_sqlite_compat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "dev")
    monkeypatch.delenv("GENOMEAI_RUNTIME_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("GENOMEAI_RUNTIME_POSTGRES_DSN", raising=False)
    runtime = resolve_runtime_storage_settings(
        project_root=tmp_path,
        storage_dir=tmp_path / "web_storage",
        sqlite_db_path=tmp_path / "web_storage" / "web.db",
    )
    diag = runtime_storage_diagnostics(runtime)
    assert runtime.backend == "sqlite"
    assert runtime.compat_mode is True
    assert diag.sqlite_access_allowed is True
    assert diag.migration_status == "sqlite_compat_runtime"


def test_t34_01_prod_profile_requires_postgres_dsn(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "prod")
    monkeypatch.setenv("GENOMEAI_RUNTIME_STORAGE_BACKEND", "postgres")
    monkeypatch.delenv("GENOMEAI_RUNTIME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("GENOMEAI_RUNTIME_POSTGRES_DSN_FILE", raising=False)
    runtime = resolve_runtime_storage_settings(
        project_root=tmp_path,
        storage_dir=tmp_path / "web_storage",
        sqlite_db_path=tmp_path / "web_storage" / "web.db",
    )
    with pytest.raises(RuntimeStorageConfigError, match="GENOMEAI_RUNTIME_POSTGRES_DSN"):
        validate_runtime_storage_settings(runtime)


def test_t34_01_prod_profile_forbids_sqlite_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "prod")
    monkeypatch.setenv("GENOMEAI_RUNTIME_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("GENOMEAI_RUNTIME_POSTGRES_DSN", "postgresql://genomeai:secret@postgres:5432/genomeai")
    with pytest.raises(RuntimeStorageConfigError, match="legacy SQLite path"):
        validate_runtime_storage_settings(
            resolve_runtime_storage_settings(
                project_root=tmp_path,
                storage_dir=tmp_path / "web_storage",
                sqlite_db_path=tmp_path / "web_storage" / "web.db",
            )
        )


def test_t34_01_sqlite_connect_guard_blocks_adult_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "stage")
    monkeypatch.setenv("GENOMEAI_RUNTIME_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("GENOMEAI_RUNTIME_POSTGRES_DSN", "postgresql://genomeai:secret@postgres:5432/genomeai")
    with pytest.raises(RuntimeStorageConfigError, match=r"SQLite compat connect\(\) запрещён при active backend=postgres"):
        validate_sqlite_compat_access(
            db_path=tmp_path / "web_storage" / "web.db",
            project_root=tmp_path,
            storage_dir=tmp_path / "web_storage",
        )


def test_t34_01_deploy_guard_exposes_runtime_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "dev")
    monkeypatch.setenv("GENOMEAI_WEB_SECRET", "dev-secret-change-me")
    monkeypatch.delenv("GENOMEAI_RUNTIME_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("GENOMEAI_RUNTIME_POSTGRES_DSN", raising=False)
    settings = get_settings()
    cfg = validate_runtime_config(settings=settings)
    assert cfg["runtime_storage"]["backend"] == "sqlite"
    assert cfg["runtime_storage"]["migration_status"] == "sqlite_compat_runtime"


def test_t34_01_stage_runtime_reports_storage_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    secret_file = tmp_path / "session.secret"
    secret_file.write_text("stage-secret-long-enough", encoding="utf-8")
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "stage")
    monkeypatch.setenv("GENOMEAI_WEB_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("GENOMEAI_RUNTIME_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("GENOMEAI_RUNTIME_POSTGRES_DSN", "postgresql://genomeai:secret@postgres:5432/genomeai")
    settings = get_settings()
    with pytest.raises(DeployConfigError, match="runtime storage invalid: .*legacy SQLite path"):
        validate_runtime_config(settings=settings)
