from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.security import ALL_PERMISSIONS
from .security_matrix import SecurityMatrixConfigError, load_permission_matrix
from core.infra.queue_runtime import (
    resolve_queue_runtime_settings,
    validate_queue_runtime_settings,
    QueueRuntimeConfigError,
)
from core.infra.runtime_storage import (
    resolve_runtime_storage_settings,
    validate_runtime_storage_settings,
    RuntimeStorageConfigError,
)
from core.ops.production_lockdown import (
    ProductionLockdownError,
    production_lockdown_report,
    validate_production_lockdown,
)


class DeployConfigError(RuntimeError):
    """Raised when deploy/runtime configuration is unsafe or invalid."""


def _read_secret(*, env_name: str) -> str:
    direct = str(os.environ.get(env_name, "") or "").strip()
    if direct:
        return direct
    file_var = f"{env_name}_FILE"
    file_path = str(os.environ.get(file_var, "") or "").strip()
    if not file_path:
        return ""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        raise DeployConfigError(
            f"{file_var} указывает на отсутствующий файл: {file_path}"
        )
    value = p.read_text(encoding="utf-8").strip()
    if not value:
        raise DeployConfigError(f"{file_var} содержит пустой секрет: {file_path}")
    return value


def load_web_session_secret(*, allow_dev_fallback: bool = True) -> str:
    value = _read_secret(env_name="GENOMEAI_WEB_SECRET")
    if value:
        return value
    if allow_dev_fallback:
        return "dev-secret-change-me"
    raise DeployConfigError(
        "Не задан секрет сессии: укажите GENOMEAI_WEB_SECRET или GENOMEAI_WEB_SECRET_FILE"
    )


def load_optional_secret(*, env_name: str) -> str:
    return _read_secret(env_name=env_name)


def _parse_positive_int(raw: str | None, *, env_name: str) -> int:
    value = str(raw or "").strip()
    if not value:
        raise DeployConfigError(f"{env_name} не задан")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise DeployConfigError(f"{env_name} должен быть целым числом, получено: {value!r}") from exc
    if parsed <= 0:
        raise DeployConfigError(f"{env_name} должен быть > 0, получено: {parsed}")
    return parsed


def validate_runtime_config(*, settings: Any) -> dict[str, Any]:
    profile = str(os.environ.get("GENOMEAI_DEPLOY_PROFILE") or "dev").strip().lower()
    if profile not in {"dev", "test", "stage", "prod", "adult"}:
        raise DeployConfigError(
            f"GENOMEAI_DEPLOY_PROFILE должен быть одним из ['adult', 'dev', 'prod', 'stage', 'test'], получено: {profile!r}"
        )

    secret = load_web_session_secret(allow_dev_fallback=(profile == "dev"))
    if profile == "prod" and secret == "dev-secret-change-me":
        raise DeployConfigError(
            "В prod запрещен секрет по умолчанию 'dev-secret-change-me'. Укажите GENOMEAI_WEB_SECRET или GENOMEAI_WEB_SECRET_FILE"
        )
    if profile == "prod" and len(secret) < 12:
        raise DeployConfigError(
            "GENOMEAI_WEB_SECRET слишком короткий: минимум 12 символов для надежной сессионной подписи"
        )

    # Numeric guardrails: clear startup errors before accepting traffic.
    _parse_positive_int(os.environ.get("GENOMEAI_WEB_MAX_UPLOAD_MB", "200"), env_name="GENOMEAI_WEB_MAX_UPLOAD_MB")
    _parse_positive_int(os.environ.get("GENOMEAI_WEB_MAX_MAPPING_MB", "5"), env_name="GENOMEAI_WEB_MAX_MAPPING_MB")
    _parse_positive_int(os.environ.get("GENOMEAI_JOB_TIMEOUT_SEC", "1800"), env_name="GENOMEAI_JOB_TIMEOUT_SEC")
    _parse_positive_int(
        os.environ.get("GENOMEAI_CONNECTOR_RECOVERY_QUEUE_LIMIT", "5"),
        env_name="GENOMEAI_CONNECTOR_RECOVERY_QUEUE_LIMIT",
    )

    try:
        matrix = load_permission_matrix(settings.project_root)
    except SecurityMatrixConfigError as exc:
        raise DeployConfigError(f"Матрица прав невалидна: {exc}") from exc

    known_permissions = set(ALL_PERMISSIONS)
    for action_key, meta in (matrix.get("actions") or {}).items():
        unknown = [p for p in (meta.get("permissions") or []) if p not in known_permissions]
        if unknown:
            raise DeployConfigError(
                f"Матрица прав actions.{action_key} содержит неизвестные permissions: {', '.join(sorted(unknown))}"
            )

    # Optional secrets should also fail early when file indirection is broken.
    load_optional_secret(env_name="OPENAI_API_KEY")

    try:
        runtime = resolve_runtime_storage_settings(
            project_root=settings.project_root,
            storage_dir=settings.storage_dir,
            sqlite_db_path=getattr(settings, "db_path", Path(settings.storage_dir) / "web.db"),
        )
        storage_diag = validate_runtime_storage_settings(runtime)
    except RuntimeStorageConfigError as exc:
        raise DeployConfigError(f"runtime storage invalid: {exc}") from exc

    try:
        queue_runtime = resolve_queue_runtime_settings()
        queue_diag = validate_queue_runtime_settings(queue_runtime)
    except QueueRuntimeConfigError as exc:
        raise DeployConfigError(f"queue runtime invalid: {exc}") from exc

    if queue_runtime.adult_mode and str(queue_runtime.backend or "postgres") == "redis" and os.environ.get("GENOMEAI_WEB_DISABLE_WORKER") != "1":
        raise DeployConfigError(
            "adult redis queue contour требует GENOMEAI_WEB_DISABLE_WORKER=1; backend/web process не должен исполнять background jobs сам"
        )

    try:
        lockdown = validate_production_lockdown(settings=settings)
    except ProductionLockdownError as exc:
        raise DeployConfigError(f"production lockdown invalid: {exc}") from exc

    # Best-effort readiness of configured roots.
    for path_value, label in [
        (settings.project_root, "GENOMEAI_PROJECT_ROOT"),
        (settings.storage_dir, "GENOMEAI_WEB_STORAGE"),
        (settings.artifacts_root, "GENOMEAI_ARTIFACTS_ROOT"),
    ]:
        path = Path(path_value)
        if label == "GENOMEAI_PROJECT_ROOT":
            if not path.exists() or not path.is_dir():
                raise DeployConfigError(f"{label} должен указывать на существующую директорию: {path}")
        else:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".startup_probe"
            try:
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
            except Exception as exc:
                raise DeployConfigError(f"{label} недоступен для записи: {path}: {exc}") from exc

    return {
        "profile": profile,
        "permission_matrix_version": int(matrix.get("version") or 1),
        "openai_enabled": bool(load_optional_secret(env_name="OPENAI_API_KEY")),
        "runtime_storage": storage_diag.as_dict(),
        "queue_runtime": queue_diag.as_dict(),
        "production_lockdown": lockdown.as_dict(),
    }
