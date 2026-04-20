from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.application.ml_artifacts import resolve_model_dir, resolve_scoring_dir

from .decision_log import init_decision_log
from .versioning import generate_run_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_pack_decision_log_created_at(*, artifacts_root: Path, data_version: str, scoring_run: str) -> str:
    scoring_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
    scoring_summary = scoring_dir / "scoring_summary.json"
    if scoring_summary.exists():
        try:
            payload = json.loads(scoring_summary.read_text(encoding="utf-8"))
            created_at_utc = str(payload.get("created_at_utc") or "").strip()
            if created_at_utc:
                return created_at_utc
        except Exception:
            pass
    return "2000-01-01T00:00:00+00:00"


def _copytree(src: Path, dst: Path, include_globs: Optional[List[str]] = None) -> List[str]:
    copied: List[str] = []
    if not src.exists():
        return copied

    dst.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, dst / src.name)
        return [str((dst / src.name).resolve())]

    globs = include_globs or ["*"]
    for pat in globs:
        for p in src.glob(pat):
            if p.is_dir():
                # shallow copy for known dirs; recursive copy for leaf folders
                shutil.copytree(p, dst / p.name, dirs_exist_ok=True)
                copied.append(str((dst / p.name).resolve()))
            elif p.is_file():
                shutil.copy2(p, dst / p.name)
                copied.append(str((dst / p.name).resolve()))
    return copied


@dataclass
class PilotPackSummary:
    schema: str
    created_at_utc: str
    data_version: str
    qc_run: str
    model_version: str
    scoring_run: str
    report_version: str
    pack_id: str
    inputs: Dict[str, str]
    outputs: Dict[str, str]
    file_manifest: Dict[str, str]


def build_pilot_pack(
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: str,
    scoring_run: str,
    report_version: str,
    pack_id: Optional[str] = None,
) -> Dict[str, object]:
    base = artifacts_root / data_version
    if not base.exists():
        return {"ok": False, "reason": f"data_version not found: {base}"}

    canonical_dir = base / "canonical"
    qc_dir = base / "qc" / qc_run
    model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    scoring_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
    report_dir = base / "reports" / report_version

    missing = [str(p) for p in [canonical_dir, qc_dir, model_dir, scoring_dir, report_dir] if not p.exists()]
    if missing:
        return {"ok": False, "reason": "missing required artifacts", "missing": missing}

    pid = pack_id or generate_run_id(prefix="pilot")
    out_dir = base / "pilot_packs" / pid
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ensure decision log exists (template from scoring if possible)
    decisions_paths = init_decision_log(
        artifacts_root=artifacts_root,
        data_version=data_version,
        scoring_run=scoring_run,
        user="pilot_pack",
        template_from_scoring=True,
        template_created_at_utc=_resolve_pack_decision_log_created_at(
            artifacts_root=artifacts_root,
            data_version=data_version,
            scoring_run=scoring_run,
        ),
    )
    decisions_dir = base / "decisions"

    # Copy key layers
    _copytree(canonical_dir, out_dir / "canonical")
    _copytree(qc_dir, out_dir / "qc")
    _copytree(model_dir, out_dir / "models")
    _copytree(scoring_dir, out_dir / "scoring")
    _copytree(report_dir, out_dir / "reports")
    _copytree(decisions_dir, out_dir / "decisions")

    # Minimal metadata snapshot
    meta_src = base / "metadata"
    _copytree(meta_src, out_dir / "metadata")

    # Versions linkage (single truth for the pack)
    versions = {
        "data_version": data_version,
        "qc_run": qc_run,
        "model_version": model_version,
        "scoring_run": scoring_run,
        "report_version": report_version,
        "decision_log": decisions_paths.get("csv"),
        "pack_id": pid,
    }
    _write_json(out_dir / "versions.json", versions)

    # File manifest (sha256) for reproducibility
    manifest: Dict[str, str] = {}
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(out_dir)).replace("\\", "/")
            manifest[rel] = _sha256_file(p)
    _write_json(out_dir / "pack_manifest.json", manifest)

    summary = PilotPackSummary(
        schema="genomeai.pilot_pack_summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        report_version=report_version,
        pack_id=pid,
        inputs={
            "canonical_dir": str(canonical_dir.resolve()),
            "qc_dir": str(qc_dir.resolve()),
            "model_dir": str(model_dir.resolve()),
            "scoring_dir": str(scoring_dir.resolve()),
            "report_dir": str(report_dir.resolve()),
            "decisions_dir": str(decisions_dir.resolve()),
        },
        outputs={
            "pack_dir": str(out_dir.resolve()),
            "versions_json": str((out_dir / "versions.json").resolve()),
            "pack_manifest": str((out_dir / "pack_manifest.json").resolve()),
        },
        file_manifest=manifest,
    )
    _write_json(out_dir / "pilot_pack_summary.json", asdict(summary))

    # Zip pack
    zip_path = shutil.make_archive(str(out_dir), "zip", root_dir=str(out_dir))
    return {
        "ok": True,
        "pack_id": pid,
        "pack_dir": str(out_dir.resolve()),
        "pack_zip": str(Path(zip_path).resolve()),
        "versions": versions,
        "decisions": decisions_paths,
        "summary": asdict(summary),
    }
