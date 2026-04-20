from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.infra import ArtifactsRepo, PlaybooksRepo

from core.infra.web_db import get_settings, utcnow_iso


def _project_root() -> Path:
    return Path(os.environ.get("GENOMEAI_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    settings = get_settings()
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    try:
        return repo.read_yaml(path)
    except Exception:
        return {}


def normalize_target_kind(kind: str) -> str:
    k = str(kind or "").strip().lower()
    if k not in ("alert", "task"):
        raise ValueError(f"invalid_target_kind: expected 'alert'|'task', got {kind}")
    return k


def normalize_target_type(tp: str) -> str:
    t = str(tp or "").strip()
    if not t:
        raise ValueError("target_type_required")
    return t


def normalize_farm_id(farm_id: Optional[str]) -> str:
    return str(farm_id or "").strip()


def make_playbook_key(*, target_kind: str, target_type: str) -> str:
    k = normalize_target_kind(target_kind)
    t = normalize_target_type(target_type)
    return f"{k}:{t}"


@dataclass
class PlaybookCreate:
    target_kind: str
    target_type: str
    farm_id: str = ""
    name: str = ""
    description: str = ""
    steps: list[dict[str, Any]] | None = None
    comment: str = ""
    set_active: bool = True


def _slugify(s: str) -> str:
    s = str(s or "").strip().lower()
    if not s:
        return "step"
    out = []
    prev_us = False
    for ch in s:
        ok = ch.isalnum()
        if ok:
            out.append(ch)
            prev_us = False
        else:
            if not prev_us and out:
                out.append("_")
            prev_us = True
    ss = "".join(out).strip("_")
    return ss or "step"


def normalize_steps(steps: Any) -> list[dict[str, Any]]:
    if steps is None:
        return []
    if not isinstance(steps, list):
        raise ValueError("steps_must_be_list")

    out: list[dict[str, Any]] = []
    used: set[str] = set()
    for it in steps:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        details = str(it.get("details") or "").strip() or None
        required = bool(it.get("required", False))
        key_raw = str(it.get("key") or "").strip() or _slugify(title)
        key = _slugify(key_raw)
        base = key
        n = 2
        while key in used:
            key = f"{base}_{n}"
            n += 1
        used.add(key)
        out.append({"key": key, "title": title, "details": details, "required": required})
    return out


def create_playbook_version(
    conn,
    *,
    tenant_id: str,
    pb: PlaybookCreate,
    created_by: Optional[int] = None,
    created_by_username: Optional[str] = None,
) -> str:
    kind = normalize_target_kind(pb.target_kind)
    tp = normalize_target_type(pb.target_type)
    farm_id = normalize_farm_id(pb.farm_id)
    name = str(pb.name or "").strip() or f"Playbook: {kind}.{tp}"
    desc = str(pb.description or "").strip() or None
    steps = normalize_steps(pb.steps or [])

    version_id = uuid.uuid4().hex
    playbook_key = make_playbook_key(target_kind=kind, target_type=tp)
    repo = PlaybooksRepo(conn)
    repo.create_version(
        tenant_id=tenant_id,
        version_id=version_id,
        playbook_key=playbook_key,
        target_kind=kind,
        target_type=tp,
        farm_id=farm_id,
        name=name,
        description=desc,
        steps=steps,
        created_at=utcnow_iso(),
        created_by=int(created_by) if created_by is not None else None,
        created_by_username=str(created_by_username) if created_by_username else None,
        comment=(str(pb.comment).strip() if pb.comment else None),
    )
    if bool(pb.set_active):
        set_active_playbook(conn, tenant_id=tenant_id, playbook_key=playbook_key, farm_id=farm_id, version_id=version_id)
    return version_id


def get_active_version_state(conn, *, tenant_id: str, playbook_key: str, farm_id: str) -> dict[str, Any]:
    repo = PlaybooksRepo(conn)
    return repo.get_active_version_mapping(tenant_id=tenant_id, playbook_key=playbook_key, farm_id=normalize_farm_id(farm_id))


def set_active_playbook(conn, *, tenant_id: str, playbook_key: str, farm_id: str, version_id: str) -> None:
    if not str(version_id or "").strip():
        raise ValueError("version_id_required")
    if not str(playbook_key or "").strip():
        raise ValueError("playbook_key_required")
    fid = normalize_farm_id(farm_id)
    repo = PlaybooksRepo(conn)
    row = repo.get_version(tenant_id=tenant_id, version_id=version_id)
    if not row:
        raise KeyError("playbook_version_not_found")
    if str(row["playbook_key"]) != str(playbook_key):
        raise ValueError("version_key_mismatch")
    if str(row.get("farm_id") or "") != str(fid):
        raise ValueError("version_farm_mismatch")
    repo.set_active_version(tenant_id=tenant_id, playbook_key=playbook_key, farm_id=fid, version_id=version_id, updated_at=utcnow_iso())


def _fetch_version(conn, *, tenant_id: str, version_id: str) -> Optional[dict[str, Any]]:
    return PlaybooksRepo(conn).get_version(tenant_id=tenant_id, version_id=version_id)


def get_version(conn, *, tenant_id: str, version_id: str) -> Optional[dict[str, Any]]:
    return _fetch_version(conn, tenant_id=tenant_id, version_id=version_id)


def get_active_playbook(
    conn,
    *,
    tenant_id: str,
    target_kind: str,
    target_type: str,
    farm_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    kind = normalize_target_kind(target_kind)
    tp = normalize_target_type(target_type)
    key = make_playbook_key(target_kind=kind, target_type=tp)
    fid = normalize_farm_id(farm_id)
    repo = PlaybooksRepo(conn)
    rows = repo.list_active_candidates(tenant_id=tenant_id, playbook_key=key, farm_id=fid)
    if not rows:
        return None
    vid = None
    for r in rows:
        v = str(r.get("active_version_id") or "").strip()
        if v:
            vid = v
            break
    if not vid:
        return None
    return _fetch_version(conn, tenant_id=tenant_id, version_id=vid)


def list_versions(
    conn,
    *,
    tenant_id: str,
    target_kind: Optional[str] = None,
    target_type: Optional[str] = None,
    farm_id: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    repo = PlaybooksRepo(conn)
    return repo.list_versions(
        tenant_id=tenant_id,
        target_kind=normalize_target_kind(target_kind) if target_kind else None,
        target_type=normalize_target_type(target_type) if target_type else None,
        farm_id=normalize_farm_id(farm_id) if farm_id is not None else None,
        limit=limit,
        offset=offset,
    )


def ensure_default_playbooks(conn, *, tenant_id: str = "default") -> dict[str, Any]:
    cfg = _load_yaml(_project_root() / "configs" / "playbooks" / "defaults.yaml")
    items = list(cfg.get("playbooks") or [])
    inserted = 0
    for it in items:
        try:
            kind = normalize_target_kind(it.get("target_kind") or "")
            tp = normalize_target_type(it.get("target_type") or "")
            farm_id = normalize_farm_id(it.get("farm_id"))
            key = make_playbook_key(target_kind=kind, target_type=tp)
            row = get_active_version_state(conn, tenant_id=tenant_id, playbook_key=key, farm_id=farm_id)
            if str(row.get("active_version_id") or "").strip():
                continue
            pb = PlaybookCreate(
                target_kind=kind,
                target_type=tp,
                farm_id=farm_id,
                name=str(it.get("name") or "").strip(),
                description=str(it.get("description") or "").strip(),
                steps=list(it.get("steps") or []),
                comment="seed.defaults",
                set_active=True,
            )
            create_playbook_version(conn, tenant_id=tenant_id, pb=pb, created_by=None, created_by_username="system")
            inserted += 1
        except Exception:
            continue
    return {"inserted": inserted}
