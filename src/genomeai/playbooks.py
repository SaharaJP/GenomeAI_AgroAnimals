from core.infra.postgres_compat import connect_postgres_compat as _pg_connect
from __future__ import annotations

"""T12-03: Playbooks loader for offline-core.

Offline-core must be able to embed a recommended plan of actions into reports and
Copilot answers. Playbooks are primarily stored and versioned in web DB
(web_cabinet/storage/web.db). However, offline-core MUST degrade gracefully when
web DB is unavailable or empty.

This module provides best-effort resolution:
1) Try active playbook version from SQLite (farm-specific override first, then global).
2) Fallback to defaults from configs/playbooks/defaults.yaml.

Returned playbook is a dict with normalized fields and a "source" marker.
"""

import json
import os
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Optional


def _project_root() -> Path:
    return Path(os.environ.get("GENOMEAI_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()


def _default_web_db_path() -> Path:
    # Mirror web_cabinet.db.get_settings() default location.
    pr = _project_root()
    storage_dir = Path(os.environ.get("GENOMEAI_WEB_STORAGE", pr / "web_cabinet" / "storage")).resolve()
    return storage_dir / "web.db"


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _normalize_kind(kind: str) -> str:
    k = str(kind or "").strip().lower()
    if k not in ("alert", "task"):
        raise ValueError(f"invalid_target_kind: expected 'alert'|'task', got {kind}")
    return k


def _normalize_type(tp: str) -> str:
    t = str(tp or "").strip()
    if not t:
        raise ValueError("target_type_required")
    return t


def _normalize_farm_id(fid: Optional[str]) -> str:
    return str(fid or "").strip()


def make_playbook_key(*, target_kind: str, target_type: str) -> str:
    return f"{_normalize_kind(target_kind)}:{_normalize_type(target_type)}"


def _hash_default_playbook(pb: Dict[str, Any]) -> str:
    # Stable-ish id for defaults (so we can trace it in reports when DB missing).
    blob = json.dumps(pb, ensure_ascii=False, sort_keys=True)
    return "defaults_" + sha1(blob.encode("utf-8")).hexdigest()[:16]


def _defaults_index(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    cfg_path = path or (_project_root() / "configs" / "playbooks" / "defaults.yaml")
    cfg = _load_yaml(cfg_path)
    items = list(cfg.get("playbooks") or [])
    out: Dict[str, Dict[str, Any]] = {}
    for it in items:
        try:
            kind = _normalize_kind(it.get("target_kind") or "")
            tp = _normalize_type(it.get("target_type") or "")
            farm_id = _normalize_farm_id(it.get("farm_id"))
            key = make_playbook_key(target_kind=kind, target_type=tp)
            pb = {
                "version_id": _hash_default_playbook(it),
                "tenant_id": "default",
                "playbook_key": key,
                "target_kind": kind,
                "target_type": tp,
                "farm_id": farm_id,
                "name": str(it.get("name") or "").strip() or f"Playbook: {key}",
                "description": str(it.get("description") or "").strip() or None,
                "steps": list(it.get("steps") or []),
                "source": "defaults_yaml",
                "sources": {"defaults_yaml": str(cfg_path.resolve()) if cfg_path.exists() else "NA"},
            }
            # Store by (key,farm_id). Later we resolve farm override.
            out[f"{key}|{farm_id}"] = pb
        except Exception:
            continue
    return out


def _db_fetch_active(
    *,
    db_path: Path,
    tenant_id: str,
    target_kind: str,
    target_type: str,
    farm_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    kind = _normalize_kind(target_kind)
    tp = _normalize_type(target_type)
    key = make_playbook_key(target_kind=kind, target_type=tp)
    fid = _normalize_farm_id(farm_id)

    try:
        conn = _pg_connect()

        rows = conn.execute(
            "SELECT active_version_id, farm_id FROM playbooks_active "
            "WHERE tenant_id=? AND playbook_key=? AND farm_id IN (?, '') "
            "ORDER BY CASE WHEN farm_id=? THEN 0 ELSE 1 END",
            (tenant_id, key, fid, fid),
        ).fetchall()
        vid = None
        for r in rows or []:
            v = str(r["active_version_id"] or "").strip()
            if v:
                vid = v
                break
        if not vid:
            conn.close()
            return None

        row = conn.execute(
            "SELECT * FROM playbook_versions WHERE tenant_id=? AND version_id=?",
            (tenant_id, vid),
        ).fetchone()
        conn.close()
        if not row:
            return None

        d = dict(row)
        try:
            d["steps"] = json.loads(d.get("steps_json") or "[]")
        except Exception:
            d["steps"] = []
        d.pop("steps_json", None)
        d["source"] = "web_db"
        d["sources"] = {"web_db": str(db_path.resolve()), "tables": "playbooks_active/playbook_versions"}
        return d
    except Exception:
        return None


def resolve_active_playbook(
    *,
    target_kind: str,
    target_type: str,
    farm_id: Optional[str] = None,
    tenant_id: str = "default",
    web_db_path: Optional[Path] = None,
    defaults_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve an active playbook (web DB first, then defaults.yaml).

    Returns a normalized dict with fields:
      version_id, playbook_key, target_kind, target_type, farm_id, name, description, steps,
      source, sources.
    """

    db_path = (web_db_path or _default_web_db_path()).resolve()
    pb = _db_fetch_active(db_path=db_path, tenant_id=str(tenant_id), target_kind=target_kind, target_type=target_type, farm_id=farm_id)
    if pb:
        # Keep farm_id used (as stored in version row)
        pb.setdefault("playbook_key", make_playbook_key(target_kind=target_kind, target_type=target_type))
        return pb

    idx = _defaults_index(defaults_path)
    key = make_playbook_key(target_kind=target_kind, target_type=target_type)
    fid = _normalize_farm_id(farm_id)
    # Farm override first
    if f"{key}|{fid}" in idx:
        return idx[f"{key}|{fid}"]
    # Global (tenant-wide)
    if f"{key}|" in idx:
        return idx[f"{key}|"]
    return None


def list_active_playbooks(
    *,
    tenant_id: str = "default",
    web_db_path: Optional[Path] = None,
    defaults_path: Optional[Path] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """List active playbooks (for Copilot knowledge).

    Strategy:
    - If web DB exists and has active rows -> return those joined with versions.
    - Else, return defaults (treated as active).
    """

    db_path = (web_db_path or _default_web_db_path()).resolve()
    out: List[Dict[str, Any]] = []

    try:
        if True:
            conn = _pg_connect()
            rows = conn.execute(
                "SELECT v.* FROM playbooks_active a "
                "JOIN playbook_versions v ON v.tenant_id=a.tenant_id AND v.version_id=a.active_version_id "
                "WHERE a.tenant_id=? ORDER BY v.target_kind, v.target_type, v.farm_id LIMIT ?",
                (str(tenant_id), int(limit)),
            ).fetchall()
            conn.close()
            for r in rows or []:
                d = dict(r)
                try:
                    d["steps"] = json.loads(d.get("steps_json") or "[]")
                except Exception:
                    d["steps"] = []
                d.pop("steps_json", None)
                d["source"] = "web_db"
                d["sources"] = {"web_db": str(db_path.resolve()), "tables": "playbooks_active/playbook_versions"}
                out.append(d)
        except Exception:
            out = []

    if not out:
        idx = _defaults_index(defaults_path)
        out = list(idx.values())[: int(limit)]

    return {
        "available": bool(out),
        "count": int(len(out)),
        "active": out,
        "sources": {"web_db": str(db_path.resolve()) if db_path.exists() else "NA", "defaults_yaml": str((defaults_path or (_project_root() / 'configs' / 'playbooks' / 'defaults.yaml')).resolve())},
    }
