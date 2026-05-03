from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from genomeai.versioning import write_json

_DEFAULT_CONFIG_REL = Path("configs/ml_pipeline_v1.yaml")


@dataclass(frozen=True)
class MlConfigRef:
    path: str
    config_version: str
    sha256: str
    payload: dict[str, Any]


def _project_root() -> Path:
    return Path(os.environ.get("GENOMEAI_PROJECT_ROOT", Path(__file__).resolve().parents[3])).resolve()


def default_ml_config_path() -> Path:
    return (_project_root() / _DEFAULT_CONFIG_REL).resolve()


def resolve_ml_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is None:
        return default_ml_config_path()
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = (_project_root() / path).resolve()
    return path.resolve()


def load_ml_pipeline_config(config_path: str | Path | None = None) -> MlConfigRef:
    path = resolve_ml_config_path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: expected YAML object at top level")
        raw = payload
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        sha256 = hashlib.sha256(b"{}").hexdigest()
    config_version = str(raw.get("config_version") or path.stem).strip() or path.stem
    return MlConfigRef(
        path=str(path),
        config_version=config_version,
        sha256=sha256,
        payload=raw,
    )


def register_model_manifest(
    *,
    artifacts_root: Path,
    data_version: str,
    model_version: str,
    entry: dict[str, Any],
) -> Path:
    manifest_path = Path(artifacts_root) / data_version / "metadata" / "model_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema": "genomeai.model_manifest.v1",
            "data_version": data_version,
            "models": {},
            "latest": None,
        }
    manifest.setdefault("models", {})
    manifest["data_version"] = data_version
    manifest["models"][model_version] = dict(entry)
    manifest["latest"] = model_version
    write_json(manifest_path, manifest)
    return manifest_path


def register_scoring_manifest(
    *,
    artifacts_root: Path,
    data_version: str,
    scoring_run: str,
    entry: dict[str, Any],
) -> Path:
    manifest_path = Path(artifacts_root) / data_version / "metadata" / "scoring_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema": "genomeai.scoring_manifest.v1",
            "data_version": data_version,
            "scoring_runs": {},
            "latest": None,
        }
    manifest.setdefault("scoring_runs", {})
    manifest["data_version"] = data_version
    manifest["scoring_runs"][scoring_run] = dict(entry)
    manifest["latest"] = scoring_run
    write_json(manifest_path, manifest)
    return manifest_path


def _default_web_db_path() -> Path:
    storage_dir = Path(os.environ.get("GENOMEAI_WEB_STORAGE", _project_root() / "web_cabinet" / "storage")).resolve()
    return storage_dir / "web.db"


def write_best_effort_ml_audit(
    *,
    action: str,
    object_type: str,
    object_id: str,
    data_version: str,
    run_id: str,
    after: dict[str, Any],
    status: str = "OK",
    error: str | None = None,
) -> bool:
    db_path = _default_web_db_path()
    if not db_path.exists():
        return False
    try:
        from core.audit.events import write_audit
        from core.infra.web_db import connect, init_db

        conn = connect(db_path)
        try:
            init_db(conn)
            write_audit(
                conn,
                tenant_id="default",
                user_id=0,
                username="system",
                role="Admin",
                action=action,
                object_type=object_type,
                object_id=object_id,
                data_version=data_version,
                run_id=run_id,
                after=after,
                status=status,
                error=error,
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


__all__ = [
    "MlConfigRef",
    "default_ml_config_path",
    "load_ml_pipeline_config",
    "register_model_manifest",
    "register_scoring_manifest",
    "resolve_ml_config_path",
    "write_best_effort_ml_audit",
]
