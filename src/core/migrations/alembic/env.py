from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import os

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_runtime_postgres_dsn() -> str:
    value = str(os.environ.get("GENOMEAI_RUNTIME_POSTGRES_DSN") or "").strip()
    if value:
        return value
    file_path = str(os.environ.get("GENOMEAI_RUNTIME_POSTGRES_DSN_FILE") or "").strip()
    if not file_path:
        raise RuntimeError("GENOMEAI_RUNTIME_POSTGRES_DSN or GENOMEAI_RUNTIME_POSTGRES_DSN_FILE is required for Alembic")
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"GENOMEAI_RUNTIME_POSTGRES_DSN_FILE points to missing file: {file_path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"GENOMEAI_RUNTIME_POSTGRES_DSN_FILE is empty: {file_path}")
    return value


def normalize_sqlalchemy_dsn(url: str) -> str:
    value = str(url or "").strip()
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    return value


target_metadata = None


def run_migrations_offline() -> None:
    url = normalize_sqlalchemy_dsn(get_runtime_postgres_dsn())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = normalize_sqlalchemy_dsn(get_runtime_postgres_dsn())
    connectable = create_engine(url, poolclass=pool.NullPool, future=True)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
