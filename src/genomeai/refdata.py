from __future__ import annotations

"""T11-02: Reference dictionaries (price books + assumptions) with versioning.

Storage
-------
We reuse the existing on-prem sqlite database (web_cabinet/storage/web.db by default).

Why sqlite:
- already used for RBAC/audit/saved views;
- keeps UI simple;
- versioning + rollback can be implemented deterministically.

Design
------
- Price books:
    * price_book_versions(version_id, tenant_id, effective_date, created_at, created_by, comment)
    * price_book_items(version_id, tenant_id, item_type, item_code, name, unit, currency, value, farm_id, meta_json)
- Assumptions:
    * assumptions_versions(...)
    * assumptions_items(version_id, tenant_id, key, value, unit, data_type, meta_json)
- Active pointer (rollback): refdata_active(tenant_id, kind, active_version_id)

Notes
-----
1) We do NOT delete versions. Rollback changes only the active pointer.
2) Calculations should snapshot used versions into their own run_dir (see economics_v2).
"""

import json
import math
import numbers
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_refdata_schema(conn: Any) -> None:
    """Idempotent schema init for refdata tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS refdata_active (
          tenant_id TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('price_book','assumptions')),
          active_version_id TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(tenant_id, kind)
        );

        CREATE TABLE IF NOT EXISTS price_book_versions (
          version_id TEXT PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          effective_date TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_by INTEGER,
          comment TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_price_book_versions_tenant_eff ON price_book_versions(tenant_id, effective_date);

        CREATE TABLE IF NOT EXISTS price_book_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version_id TEXT NOT NULL,
          tenant_id TEXT NOT NULL,

          item_type TEXT NOT NULL,
          item_code TEXT NOT NULL,
          name TEXT,
          unit TEXT,
          currency TEXT,
          value REAL,

          farm_id TEXT,
          meta_json TEXT NOT NULL DEFAULT '{}',

          FOREIGN KEY(version_id) REFERENCES price_book_versions(version_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_price_book_items_ver ON price_book_items(version_id);
        CREATE INDEX IF NOT EXISTS idx_price_book_items_type_code ON price_book_items(tenant_id, item_type, item_code);

        CREATE TABLE IF NOT EXISTS assumptions_versions (
          version_id TEXT PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          effective_date TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_by INTEGER,
          comment TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_assumptions_versions_tenant_eff ON assumptions_versions(tenant_id, effective_date);

        CREATE TABLE IF NOT EXISTS assumptions_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version_id TEXT NOT NULL,
          tenant_id TEXT NOT NULL,

          key TEXT NOT NULL,
          value TEXT,
          unit TEXT,
          data_type TEXT NOT NULL DEFAULT 'str' CHECK(data_type IN ('str','int','float','bool','json')),
          meta_json TEXT NOT NULL DEFAULT '{}',

          FOREIGN KEY(version_id) REFERENCES assumptions_versions(version_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_assumptions_items_ver ON assumptions_items(version_id);
        CREATE INDEX IF NOT EXISTS idx_assumptions_items_key ON assumptions_items(tenant_id, key);
        """
    )
    conn.commit()


def _rowdicts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def _maybe_parse(value: str | None, data_type: str) -> Any:
    if value is None:
        return None
    t = (data_type or "str").strip().lower()
    if t == "str":
        return str(value)
    if t == "int":
        try:
            return int(float(value))
        except Exception:
            return None
    if t == "float":
        try:
            return float(value)
        except Exception:
            return None
    if t == "bool":
        v = str(value).strip().lower()
        return v in {"1", "true", "yes", "y", "on"}
    if t == "json":
        try:
            return json.loads(value)
        except Exception:
            return None
    return str(value)


def _infer_data_type(value: Any) -> str:
    """Infer assumptions data_type for serialization/parsing.

    This is used on UI imports where CSV values may be numeric.

    Heuristics:
      - bool -> bool
      - integers -> int
      - other numbers -> float
      - dict/list -> json
      - strings: try bool/int/float patterns, else str
    """

    if value is None:
        return "str"

    # pandas/np NaN
    try:
        if isinstance(value, float) and math.isnan(value):
            return "str"
    except Exception:
        pass

    if isinstance(value, bool):
        return "bool"

    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return "int"

    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return "float"

    if isinstance(value, (dict, list)):
        return "json"

    s = str(value).strip()
    if s.lower() in {"true", "false", "1", "0", "yes", "no", "y", "n", "on", "off"}:
        return "bool"
    try:
        if s and s.replace("-", "", 1).isdigit():
            return "int"
    except Exception:
        pass
    try:
        float(s)
        return "float"
    except Exception:
        return "str"


def _users_table(conn: Any) -> str | None:
    """Return users table name (users_v2 preferred) if present in this sqlite."""
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users_v2','users') ORDER BY CASE WHEN name='users_v2' THEN 0 ELSE 1 END LIMIT 1"
        ).fetchone()
        return str(row[0]) if row else None
    except Exception:
        return None


def _normalize_price_item(it: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a price item dict from UI/CSV into internal schema shape."""
    item_type = str(it.get("item_type") or "").strip()
    item_code = str(it.get("item_code") or "").strip()
    if not item_type:
        raise ValueError("price item: item_type пуст")
    if not item_code:
        raise ValueError(f"price item: item_code пуст (type={item_type})")

    # meta: accept either meta(dict) or meta_json(str)
    meta: Dict[str, Any] = {}
    if isinstance(it.get("meta"), dict):
        meta = dict(it.get("meta") or {})
    elif it.get("meta_json") is not None:
        try:
            meta = json.loads(str(it.get("meta_json") or "{}"))
        except Exception:
            meta = {}

    # If UI provides notes field, capture it
    notes = it.get("notes")
    if notes is not None and "notes" not in meta:
        meta["notes"] = str(notes)

    v_raw = it.get("value")
    value: float | None
    if v_raw is None or str(v_raw).strip() == "":
        value = None
    else:
        try:
            value = float(v_raw)
        except Exception:
            raise ValueError(f"price item: value не число (type={item_type}, code={item_code}, value={v_raw})")

    farm_id = it.get("farm_id")
    farm_id = (None if farm_id is None or str(farm_id).strip() == "" else str(farm_id).strip())

    return {
        "item_type": item_type,
        "item_code": item_code,
        "name": (str(it.get("name")) if it.get("name") is not None else None),
        "unit": (str(it.get("unit")) if it.get("unit") is not None else None),
        "currency": (str(it.get("currency")) if it.get("currency") is not None else None),
        "value": value,
        "farm_id": farm_id,
        "meta": meta,
    }


def _normalize_assumption_item(it: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an assumption item dict from UI/CSV into internal schema shape."""
    key = str(it.get("key") or "").strip()
    if not key:
        raise ValueError("assumptions item: key пуст")

    # meta: accept note, meta_json
    meta: Dict[str, Any] = {}
    if isinstance(it.get("meta"), dict):
        meta = dict(it.get("meta") or {})
    elif it.get("meta_json") is not None:
        try:
            meta = json.loads(str(it.get("meta_json") or "{}"))
        except Exception:
            meta = {}

    note = it.get("note")
    if note is not None and "note" not in meta:
        meta["note"] = str(note)

    unit = it.get("unit")
    unit_s = (None if unit is None or str(unit).strip() == "" else str(unit).strip())

    dtype = str(it.get("data_type") or "").strip().lower()
    if not dtype:
        dtype = _infer_data_type(it.get("value"))
    if dtype not in {"str", "int", "float", "bool", "json"}:
        dtype = "str"

    v = it.get("value")
    if v is None or (isinstance(v, float) and (v != v)):
        v_str = None
    elif dtype == "json":
        try:
            v_str = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        except Exception:
            v_str = None if v is None else str(v)
    elif dtype == "bool":
        vv = v
        if isinstance(vv, str):
            vv = vv.strip().lower() in {"1", "true", "yes", "y", "on"}
        v_str = "true" if bool(vv) else "false"
    else:
        v_str = None if v is None else str(v)

    return {
        "key": key,
        "value": v_str,
        "unit": unit_s,
        "data_type": dtype,
        "meta": meta,
    }


@dataclass
class RefdataStore:
    """A minimal facade over sqlite refdata tables."""

    conn: Any

    def ensure(self) -> None:
        ensure_refdata_schema(self.conn)

    # --- active pointers ---

    def get_active_version(self, *, tenant_id: str, kind: str) -> str | None:
        row = self.conn.execute(
            "SELECT active_version_id FROM refdata_active WHERE tenant_id=? AND kind=?",
            (tenant_id, kind),
        ).fetchone()
        return str(row[0]) if row and row[0] else None

    def set_active_version(self, *, tenant_id: str, kind: str, version_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO refdata_active(tenant_id, kind, active_version_id, updated_at)
            VALUES(?,?,?,?)
            ON CONFLICT(tenant_id, kind)
            DO UPDATE SET active_version_id=excluded.active_version_id, updated_at=excluded.updated_at
            """,
            (tenant_id, kind, version_id, _utc_ts()),
        )
        self.conn.commit()

    # --- price books ---

    def list_price_versions(self, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        ut = _users_table(self.conn)
        if ut:
            rows = self.conn.execute(
                f"""
                SELECT v.*,
                       u.username AS created_by_username,
                       CASE WHEN v.version_id = a.active_version_id THEN 'active' ELSE 'inactive' END AS status
                FROM price_book_versions v
                LEFT JOIN {ut} u
                       ON u.id = v.created_by AND u.tenant_id = v.tenant_id
                LEFT JOIN refdata_active a
                       ON a.tenant_id = v.tenant_id AND a.kind = 'price_book'
                WHERE v.tenant_id=?
                ORDER BY v.effective_date DESC, v.created_at DESC
                LIMIT ?
                """,
                (tenant_id, int(limit)),
            ).fetchall()
            return _rowdicts(rows)

        rows = self.conn.execute(
            """
            SELECT v.*,
                   CASE WHEN v.version_id = a.active_version_id THEN 'active' ELSE 'inactive' END AS status
            FROM price_book_versions v
            LEFT JOIN refdata_active a
                   ON a.tenant_id = v.tenant_id AND a.kind = 'price_book'
            WHERE v.tenant_id=?
            ORDER BY v.effective_date DESC, v.created_at DESC
            LIMIT ?
            """,
            (tenant_id, int(limit)),
        ).fetchall()
        return _rowdicts(rows)

    def get_price_version(self, *, tenant_id: str, version_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM price_book_versions WHERE tenant_id=? AND version_id=?",
            (tenant_id, version_id),
        ).fetchone()
        return dict(row) if row else None

    def get_price_items(self, *, tenant_id: str, version_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM price_book_items
            WHERE tenant_id=? AND version_id=?
            ORDER BY item_type, item_code, COALESCE(farm_id,'')
            """,
            (tenant_id, version_id),
        ).fetchall()
        return _rowdicts(rows)

    def create_price_version(
        self,
        *,
        tenant_id: str,
        effective_date: str,
        created_by: int | None,
        comment: str | None,
        base_version_id: str | None = None,
        items: list[dict[str, Any]] | None = None,
        set_active: bool = True,
    ) -> str:
        """Create a new price book version.

        If base_version_id is provided and items is None, items are cloned from base.
        """
        vid = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO price_book_versions(version_id, tenant_id, effective_date, created_at, created_by, comment)
            VALUES(?,?,?,?,?,?)
            """,
            (vid, tenant_id, str(effective_date), _utc_ts(), int(created_by) if created_by is not None else None, comment),
        )

        if items is None and base_version_id:
            base_items = self.get_price_items(tenant_id=tenant_id, version_id=base_version_id)
            items = [
                {
                    "item_type": i.get("item_type"),
                    "item_code": i.get("item_code"),
                    "name": i.get("name"),
                    "unit": i.get("unit"),
                    "currency": i.get("currency"),
                    "value": i.get("value"),
                    "farm_id": i.get("farm_id"),
                    "meta": json.loads(i.get("meta_json") or "{}"),
                }
                for i in base_items
            ]

        for it in items or []:
            self.conn.execute(
                """
                INSERT INTO price_book_items(
                  version_id, tenant_id, item_type, item_code, name, unit, currency, value, farm_id, meta_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    vid,
                    tenant_id,
                    str(it.get("item_type") or ""),
                    str(it.get("item_code") or ""),
                    (str(it.get("name")) if it.get("name") is not None else None),
                    (str(it.get("unit")) if it.get("unit") is not None else None),
                    (str(it.get("currency")) if it.get("currency") is not None else None),
                    (float(it.get("value")) if it.get("value") is not None and str(it.get("value")) != "" else None),
                    (str(it.get("farm_id")) if it.get("farm_id") is not None and str(it.get("farm_id")) != "" else None),
                    json.dumps(it.get("meta") or {}, ensure_ascii=False),
                ),
            )

        self.conn.commit()
        if set_active:
            self.set_active_version(tenant_id=tenant_id, kind="price_book", version_id=vid)
        return vid

    def create_price_version_from_items(
        self,
        *,
        tenant_id: str,
        effective_date: str,
        created_by: int | None,
        created_by_username: str | None = None,
        comment: str | None = None,
        base_version_id: str | None = None,
        items: list[dict[str, Any]] | None = None,
        set_active: bool = False,
    ) -> dict[str, Any]:
        """UI-friendly wrapper: normalize items and return version row as dict."""
        norm_items: list[dict[str, Any]] = []
        if items is not None:
            # Keep last value for duplicates (type+code+farm_id)
            last: dict[tuple[str, str, str | None], dict[str, Any]] = {}
            for it in items:
                n = _normalize_price_item(dict(it))
                k = (str(n.get("item_type") or ""), str(n.get("item_code") or ""), n.get("farm_id"))
                last[k] = n
            norm_items = list(last.values())

        vid = self.create_price_version(
            tenant_id=tenant_id,
            effective_date=effective_date,
            created_by=created_by,
            comment=comment,
            base_version_id=base_version_id,
            items=norm_items if items is not None else None,
            set_active=set_active,
        )

        v = self.get_price_version(tenant_id=tenant_id, version_id=vid) or {"version_id": vid, "tenant_id": tenant_id}
        # best-effort username (prefer provided, else join)
        if created_by_username:
            v["created_by_username"] = str(created_by_username)
        else:
            try:
                ut = _users_table(self.conn)
                if ut and v.get("created_by") is not None:
                    row = self.conn.execute(
                        f"SELECT username FROM {ut} WHERE tenant_id=? AND id=?",
                        (tenant_id, int(v.get("created_by"))),
                    ).fetchone()
                    if row and row[0]:
                        v["created_by_username"] = str(row[0])
            except Exception:
                pass
        return dict(v)

    # --- assumptions ---

    def list_assumptions_versions(self, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        ut = _users_table(self.conn)
        if ut:
            rows = self.conn.execute(
                f"""
                SELECT v.*,
                       u.username AS created_by_username,
                       CASE WHEN v.version_id = a.active_version_id THEN 'active' ELSE 'inactive' END AS status
                FROM assumptions_versions v
                LEFT JOIN {ut} u
                       ON u.id = v.created_by AND u.tenant_id = v.tenant_id
                LEFT JOIN refdata_active a
                       ON a.tenant_id = v.tenant_id AND a.kind = 'assumptions'
                WHERE v.tenant_id=?
                ORDER BY v.effective_date DESC, v.created_at DESC
                LIMIT ?
                """,
                (tenant_id, int(limit)),
            ).fetchall()
            return _rowdicts(rows)

        rows = self.conn.execute(
            """
            SELECT v.*,
                   CASE WHEN v.version_id = a.active_version_id THEN 'active' ELSE 'inactive' END AS status
            FROM assumptions_versions v
            LEFT JOIN refdata_active a
                   ON a.tenant_id = v.tenant_id AND a.kind = 'assumptions'
            WHERE v.tenant_id=?
            ORDER BY v.effective_date DESC, v.created_at DESC
            LIMIT ?
            """,
            (tenant_id, int(limit)),
        ).fetchall()
        return _rowdicts(rows)

    def get_assumptions_version(self, *, tenant_id: str, version_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM assumptions_versions WHERE tenant_id=? AND version_id=?",
            (tenant_id, version_id),
        ).fetchone()
        return dict(row) if row else None

    def get_assumptions_items(self, *, tenant_id: str, version_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM assumptions_items
            WHERE tenant_id=? AND version_id=?
            ORDER BY key
            """,
            (tenant_id, version_id),
        ).fetchall()
        return _rowdicts(rows)

    def create_assumptions_version(
        self,
        *,
        tenant_id: str,
        effective_date: str,
        created_by: int | None,
        comment: str | None,
        base_version_id: str | None = None,
        items: list[dict[str, Any]] | None = None,
        set_active: bool = True,
    ) -> str:
        vid = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO assumptions_versions(version_id, tenant_id, effective_date, created_at, created_by, comment)
            VALUES(?,?,?,?,?,?)
            """,
            (vid, tenant_id, str(effective_date), _utc_ts(), int(created_by) if created_by is not None else None, comment),
        )

        if items is None and base_version_id:
            base_items = self.get_assumptions_items(tenant_id=tenant_id, version_id=base_version_id)
            items = [
                {
                    "key": i.get("key"),
                    "value": i.get("value"),
                    "unit": i.get("unit"),
                    "data_type": i.get("data_type"),
                    "meta": json.loads(i.get("meta_json") or "{}"),
                }
                for i in base_items
            ]

        for it in items or []:
            self.conn.execute(
                """
                INSERT INTO assumptions_items(version_id, tenant_id, key, value, unit, data_type, meta_json)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    vid,
                    tenant_id,
                    str(it.get("key") or ""),
                    (None if it.get("value") is None else str(it.get("value"))),
                    (str(it.get("unit")) if it.get("unit") is not None else None),
                    str(it.get("data_type") or "str"),
                    json.dumps(it.get("meta") or {}, ensure_ascii=False),
                ),
            )

        self.conn.commit()
        if set_active:
            self.set_active_version(tenant_id=tenant_id, kind="assumptions", version_id=vid)
        return vid

    def create_assumptions_version_from_items(
        self,
        *,
        tenant_id: str,
        effective_date: str,
        created_by: int | None,
        created_by_username: str | None = None,
        comment: str | None = None,
        base_version_id: str | None = None,
        items: list[dict[str, Any]] | None = None,
        set_active: bool = False,
    ) -> dict[str, Any]:
        """UI-friendly wrapper: normalize items and return version row as dict."""

        norm_items: list[dict[str, Any]] = []
        if items is not None:
            # Keep last value for duplicates (key)
            last: dict[str, dict[str, Any]] = {}
            for it in items:
                n = _normalize_assumption_item(dict(it))
                last[str(n.get("key") or "").strip()] = n
            norm_items = list(last.values())

        vid = self.create_assumptions_version(
            tenant_id=tenant_id,
            effective_date=effective_date,
            created_by=created_by,
            comment=comment,
            base_version_id=base_version_id,
            items=norm_items if items is not None else None,
            set_active=set_active,
        )

        v = self.get_assumptions_version(tenant_id=tenant_id, version_id=vid) or {"version_id": vid, "tenant_id": tenant_id}
        if created_by_username:
            v["created_by_username"] = str(created_by_username)
        else:
            try:
                ut = _users_table(self.conn)
                if ut and v.get("created_by") is not None:
                    row = self.conn.execute(
                        f"SELECT username FROM {ut} WHERE tenant_id=? AND id=?",
                        (tenant_id, int(v.get("created_by"))),
                    ).fetchone()
                    if row and row[0]:
                        v["created_by_username"] = str(row[0])
            except Exception:
                pass
        return dict(v)

    # --- helpers for calculations ---

    def load_assumptions_as_dict(self, *, tenant_id: str, version_id: str) -> dict[str, Any]:
        items = self.get_assumptions_items(tenant_id=tenant_id, version_id=version_id)
        out: dict[str, Any] = {}
        for it in items:
            k = str(it.get("key") or "").strip()
            if not k:
                continue
            out[k] = _maybe_parse(it.get("value"), str(it.get("data_type") or "str"))
        return out

    def load_prices_as_dict(self, *, tenant_id: str, version_id: str) -> dict[str, Any]:
        items = self.get_price_items(tenant_id=tenant_id, version_id=version_id)
        out: dict[str, Any] = {}
        for it in items:
            t = str(it.get("item_type") or "").strip()
            c = str(it.get("item_code") or "").strip()
            if not t or not c:
                continue
            key = f"{t}.{c}"
            out[key] = {
                "value": it.get("value"),
                "currency": it.get("currency"),
                "unit": it.get("unit"),
                "name": it.get("name"),
                "farm_id": it.get("farm_id"),
            }
        return out


def connect_sqlite(db_path: Path) -> Any:
    from core.infra.postgres_compat import connect_postgres_compat
    return connect_postgres_compat()
