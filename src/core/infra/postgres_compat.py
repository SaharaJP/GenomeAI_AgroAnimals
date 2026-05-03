from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.infra.runtime_storage import resolve_runtime_storage_settings
from core.infra.web_db import get_settings

try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None


def _translate_qmark_sql(sql: str) -> str:
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == '?' and not in_single and not in_double:
            out.append('%s')
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


class CompatRow(dict):
    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CompatCursor:
    def __init__(self, cur: Any):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return CompatRow(dict(row))

    def fetchall(self):
        rows = self._cur.fetchall()
        return [CompatRow(dict(r)) for r in rows]

    @property
    def lastrowid(self) -> Any:
        try:
            aux = self._cur.connection.cursor()
            aux.execute("SELECT LASTVAL() AS id")
            row = aux.fetchone()
            if row is None:
                return None
            if isinstance(row, dict):
                return row.get("id")
            try:
                return row[0]
            except Exception:
                return getattr(row, "id", None)
        except Exception as exc:
            raise AttributeError("lastrowid") from exc

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cur, name)


class CompatConnection:
    _genomeai_backend = 'postgres_compat'

    def __init__(self, conn: Any):
        self._conn = conn

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        cur = self._conn.cursor()
        cur.execute(_translate_qmark_sql(sql), tuple(params or ()))
        return CompatCursor(cur)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                self.rollback()
            except Exception:
                pass
        self.close()
        return False


def connect_postgres_compat():
    settings = get_settings()
    runtime = resolve_runtime_storage_settings(
        project_root=settings.project_root,
        storage_dir=settings.storage_dir,
        sqlite_db_path=settings.db_path,
    )
    dsn = str(runtime.postgres_dsn or '').strip()
    if not dsn:
        raise RuntimeError('adult postgres backend active but GENOMEAI_RUNTIME_POSTGRES_DSN/DATABASE_URL is missing')
    if psycopg is None or dict_row is None:
        raise RuntimeError('adult postgres backend active but psycopg is unavailable inside backend image')
    conn = psycopg.connect(dsn, row_factory=dict_row)
    return CompatConnection(conn)
