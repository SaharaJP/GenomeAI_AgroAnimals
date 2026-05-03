from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, Protocol


class DbBackend(Protocol):
    name: str

    def placeholders(self, count: int) -> str:
        ...


@dataclass(frozen=True)
class InfraDbConfig:
    backend: str = "postgres"
    dsn: Optional[str] = None


@dataclass(frozen=True)
class SQLiteBackend:
    name: str = "sqlite"

    def placeholders(self, count: int) -> str:
        return ",".join("?" for _ in range(max(0, int(count))))


@dataclass(frozen=True)
class PostgresBackend:
    name: str = "postgres"

    def placeholders(self, count: int) -> str:
        return ",".join("%s" for _ in range(max(0, int(count))))


DEFAULT_DB_CONFIG = InfraDbConfig()


def resolve_db_config(*, backend: str | None = None, dsn: str | None = None) -> InfraDbConfig:
    raw_backend = str(backend or os.environ.get("GENOMEAI_DB_BACKEND") or DEFAULT_DB_CONFIG.backend).strip().lower()
    if raw_backend not in {"sqlite", "postgres"}:
        raise ValueError(f"unsupported_db_backend: expected sqlite|postgres, got {raw_backend}")
    resolved_dsn = str(dsn or os.environ.get("GENOMEAI_DB_DSN") or "").strip() or None
    return InfraDbConfig(backend=raw_backend, dsn=resolved_dsn)


def resolve_db_backend(
    *,
    backend: str | None = None,
    dsn: str | None = None,
    conn: Any | None = None,
) -> DbBackend:
    cfg = resolve_db_config(backend=backend, dsn=dsn)
    if cfg.backend == "postgres":
        return PostgresBackend()
    return SQLiteBackend()


__all__ = [
    "DEFAULT_DB_CONFIG",
    "DbBackend",
    "InfraDbConfig",
    "PostgresBackend",
    "SQLiteBackend",
    "resolve_db_backend",
    "resolve_db_config",
]
