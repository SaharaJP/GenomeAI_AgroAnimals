from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ADULT_RUNTIME_PROFILES = {"adult", "prod", "stage"}
COMPAT_RUNTIME_PROFILES = {"dev", "test", "local"}
SUPPORTED_RUNTIME_PROFILES = ADULT_RUNTIME_PROFILES | COMPAT_RUNTIME_PROFILES
SUPPORTED_RUNTIME_BACKENDS = {"sqlite", "postgres"}
DEFAULT_SQLITE_FILENAME = "web.db"


class RuntimeStorageConfigError(RuntimeError):
    """Raised when runtime storage config is unsafe or incomplete."""


@dataclass(frozen=True)
class RuntimeStorageSettings:
    profile: str
    backend: str
    project_root: Path
    storage_dir: Path
    sqlite_db_path: Path
    postgres_dsn: str | None
    postgres_driver_available: bool
    alembic_ini_path: Path
    alembic_versions_dir: Path
    adult_mode: bool
    compat_mode: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["project_root"] = str(self.project_root)
        payload["storage_dir"] = str(self.storage_dir)
        payload["sqlite_db_path"] = str(self.sqlite_db_path)
        payload["alembic_ini_path"] = str(self.alembic_ini_path)
        payload["alembic_versions_dir"] = str(self.alembic_versions_dir)
        payload["postgres_dsn"] = redact_postgres_dsn(self.postgres_dsn)
        return payload


@dataclass(frozen=True)
class RuntimeStorageDiagnostics:
    profile: str
    backend: str
    adult_mode: bool
    compat_mode: bool
    sqlite_db_path: str
    sqlite_access_allowed: bool
    sqlite_forbidden: bool
    postgres_dsn_present: bool
    postgres_dsn_redacted: str | None
    postgres_driver_available: bool
    alembic_ini_exists: bool
    alembic_versions_dir_exists: bool
    migration_status: str
    startup_sanity: str
    forbidden_fallback_detected: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeSchemaStatus:
    component: str
    version: int | None
    status: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_secret(*, env_name: str) -> str:
    direct = str(os.environ.get(env_name, "") or "").strip()
    if direct:
        return direct
    file_var = f"{env_name}_FILE"
    file_path = str(os.environ.get(file_var, "") or "").strip()
    if not file_path:
        return ""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise RuntimeStorageConfigError(f"{file_var} указывает на отсутствующий файл: {file_path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeStorageConfigError(f"{file_var} содержит пустое значение: {file_path}")
    return value


def normalize_runtime_profile(raw: str | None) -> str:
    profile = str(raw or "dev").strip().lower() or "dev"
    aliases = {
        "production": "prod",
        "staging": "stage",
        "development": "dev",
        "compat": "dev",
    }
    return aliases.get(profile, profile)


def is_adult_runtime_profile(profile: str) -> bool:
    return normalize_runtime_profile(profile) in ADULT_RUNTIME_PROFILES


def default_runtime_backend_for_profile(profile: str) -> str:
    return "postgres"


def read_postgres_dsn() -> str | None:
    value = _read_secret(env_name="GENOMEAI_RUNTIME_POSTGRES_DSN")
    if value:
        return value
    fallback = str(os.environ.get("DATABASE_URL", "") or "").strip()
    return fallback or None


def redact_postgres_dsn(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except Exception:
        return "***"
    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path or ""
    if username:
        netloc = f"{username}:***@{host}{port}"
    else:
        netloc = f"{host}{port}"
    return urlunsplit((parsed.scheme, netloc, database, parsed.query, parsed.fragment))


def postgres_driver_available() -> bool:
    return importlib.util.find_spec("psycopg") is not None


def resolve_runtime_storage_settings(*, project_root: str | Path, storage_dir: str | Path, sqlite_db_path: str | Path | None = None) -> RuntimeStorageSettings:
    project_root_path = Path(project_root).resolve()
    storage_dir_path = Path(storage_dir).resolve()
    profile = normalize_runtime_profile(os.environ.get("GENOMEAI_DEPLOY_PROFILE"))
    backend = str(os.environ.get("GENOMEAI_RUNTIME_STORAGE_BACKEND") or default_runtime_backend_for_profile(profile)).strip().lower()
    if backend not in SUPPORTED_RUNTIME_BACKENDS:
        raise RuntimeStorageConfigError(
            f"GENOMEAI_RUNTIME_STORAGE_BACKEND должен быть одним из {sorted(SUPPORTED_RUNTIME_BACKENDS)}, получено: {backend!r}"
        )
    db_path = Path(sqlite_db_path or (storage_dir_path / DEFAULT_SQLITE_FILENAME)).resolve()
    migrations_root = project_root_path / "src" / "core" / "migrations" / "alembic"
    return RuntimeStorageSettings(
        profile=profile,
        backend=backend,
        project_root=project_root_path,
        storage_dir=storage_dir_path,
        sqlite_db_path=db_path,
        postgres_dsn=read_postgres_dsn(),
        postgres_driver_available=postgres_driver_available(),
        alembic_ini_path=(project_root_path / "alembic.ini").resolve(),
        alembic_versions_dir=(migrations_root / "versions").resolve(),
        adult_mode=is_adult_runtime_profile(profile),
        compat_mode=not is_adult_runtime_profile(profile),
    )


def runtime_storage_diagnostics(runtime: RuntimeStorageSettings) -> RuntimeStorageDiagnostics:
    sqlite_forbidden = runtime.adult_mode and runtime.sqlite_db_path.name == DEFAULT_SQLITE_FILENAME
    sqlite_allowed = runtime.backend == "sqlite" and not runtime.adult_mode
    alembic_ini_exists = runtime.alembic_ini_path.exists()
    alembic_versions_dir_exists = runtime.alembic_versions_dir.exists() and runtime.alembic_versions_dir.is_dir()
    if runtime.backend == "postgres":
        if not runtime.postgres_dsn:
            migration_status = "blocked_missing_postgres_dsn"
            startup_sanity = "fail"
        elif not runtime.postgres_driver_available:
            migration_status = "blocked_missing_postgres_driver"
            startup_sanity = "fail"
        elif not (alembic_ini_exists and alembic_versions_dir_exists):
            migration_status = "blocked_missing_alembic_baseline"
            startup_sanity = "fail"
        else:
            migration_status = "baseline_ready_connection_pending"
            startup_sanity = "baseline_only"
    else:
        migration_status = "sqlite_compat_runtime"
        startup_sanity = "compat"
    return RuntimeStorageDiagnostics(
        profile=runtime.profile,
        backend=runtime.backend,
        adult_mode=runtime.adult_mode,
        compat_mode=runtime.compat_mode,
        sqlite_db_path=str(runtime.sqlite_db_path),
        sqlite_access_allowed=sqlite_allowed,
        sqlite_forbidden=sqlite_forbidden,
        postgres_dsn_present=bool(runtime.postgres_dsn),
        postgres_dsn_redacted=redact_postgres_dsn(runtime.postgres_dsn),
        postgres_driver_available=runtime.postgres_driver_available,
        alembic_ini_exists=alembic_ini_exists,
        alembic_versions_dir_exists=alembic_versions_dir_exists,
        migration_status=migration_status,
        startup_sanity=startup_sanity,
        forbidden_fallback_detected=sqlite_forbidden,
    )


def validate_runtime_storage_settings(runtime: RuntimeStorageSettings) -> RuntimeStorageDiagnostics:
    if runtime.profile not in SUPPORTED_RUNTIME_PROFILES:
        raise RuntimeStorageConfigError(
            f"GENOMEAI_DEPLOY_PROFILE должен быть одним из {sorted(SUPPORTED_RUNTIME_PROFILES)}, получено: {runtime.profile!r}"
        )

    diagnostics = runtime_storage_diagnostics(runtime)

    if runtime.adult_mode and runtime.backend != "postgres":
        raise RuntimeStorageConfigError(
            "adult/stage/prod profile требует GENOMEAI_RUNTIME_STORAGE_BACKEND=postgres; sqlite runtime path запрещён"
        )
    if runtime.backend == "postgres" and not runtime.postgres_dsn:
        raise RuntimeStorageConfigError(
            "Для postgres runtime обязателен GENOMEAI_RUNTIME_POSTGRES_DSN или GENOMEAI_RUNTIME_POSTGRES_DSN_FILE"
        )
    if runtime.adult_mode and runtime.sqlite_db_path.name == DEFAULT_SQLITE_FILENAME:
        raise RuntimeStorageConfigError(
            f"adult/stage/prod profile запрещает legacy SQLite path: {runtime.sqlite_db_path}"
        )
    if runtime.backend == "postgres" and not runtime.postgres_driver_available:
        raise RuntimeStorageConfigError(
            "Postgres runtime выбран, но драйвер psycopg недоступен; staged cutover foundation ещё не завершён"
        )
    if runtime.backend == "postgres" and not diagnostics.alembic_ini_exists:
        raise RuntimeStorageConfigError(
            f"Не найден alembic.ini для runtime migration discipline: {runtime.alembic_ini_path}"
        )
    if runtime.backend == "postgres" and not diagnostics.alembic_versions_dir_exists:
        raise RuntimeStorageConfigError(
            f"Не найден каталог Alembic versions: {runtime.alembic_versions_dir}"
        )

    return diagnostics


def validate_sqlite_compat_access(*, db_path: str | Path, project_root: str | Path | None = None, storage_dir: str | Path | None = None) -> RuntimeStorageDiagnostics:
    path = Path(db_path).resolve()
    root = Path(project_root).resolve() if project_root is not None else path.parent.parent.resolve()
    storage = Path(storage_dir).resolve() if storage_dir is not None else path.parent.resolve()
    runtime = resolve_runtime_storage_settings(project_root=root, storage_dir=storage, sqlite_db_path=path)
    diagnostics = runtime_storage_diagnostics(runtime)
    if runtime.backend != "sqlite":
        raise RuntimeStorageConfigError(
            f"SQLite compat connect() запрещён при active backend={runtime.backend}; requested path={path}"
        )
    if runtime.adult_mode:
        raise RuntimeStorageConfigError(
            f"adult/stage/prod profile запрещает sqlite compat connect() к {path}; active backend={runtime.backend}"
        )
    return diagnostics


__all__ = [
    "ADULT_RUNTIME_PROFILES",
    "COMPAT_RUNTIME_PROFILES",
    "DEFAULT_SQLITE_FILENAME",
    "RuntimeSchemaStatus",
    "RuntimeStorageConfigError",
    "RuntimeStorageDiagnostics",
    "RuntimeStorageSettings",
    "default_runtime_backend_for_profile",
    "is_adult_runtime_profile",
    "normalize_runtime_profile",
    "postgres_driver_available",
    "read_postgres_dsn",
    "redact_postgres_dsn",
    "resolve_runtime_storage_settings",
    "runtime_storage_diagnostics",
    "validate_runtime_storage_settings",
    "validate_sqlite_compat_access",
]
