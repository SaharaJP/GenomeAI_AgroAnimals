from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Optional

from core.migrations import MigrationCompatibilityError, validate_pilot_pack_versions


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_extract_all(zf: zipfile.ZipFile, dest: Path) -> None:
    """Safe zip extraction (prevents zip-slip)."""
    dest = dest.resolve()
    for member in zf.infolist():
        name = member.filename
        if not name:
            continue
        target = (dest / name).resolve()
        if target == dest:
            continue
        if dest not in target.parents:
            raise ValueError(f"Unsafe path in zip: {name}")
    zf.extractall(dest)


def _copytree(src: Path, dst: Path) -> int:
    """Copy src tree into dst (overwrite). Returns number of copied files."""
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(p.read_bytes())
        copied += 1
    return copied


@dataclass
class ImportPackResult:
    ok: bool
    imported_at_utc: str
    pack_zip: str
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    pack_id: Optional[str] = None
    dest_base: Optional[str] = None
    verified: bool = False
    mismatches: Optional[list[dict]] = None
    copied_files: int = 0
    import_manifest_json: Optional[str] = None
    reason: Optional[str] = None


def import_pilot_pack(
    *,
    pack_zip: Path,
    artifacts_root: Path,
    verify: bool = True,
    force: bool = False,
) -> dict:
    """Import an Offline "Pilot Pack" zip into Target artifacts layout.

    Offline artifact used for transfer: artifacts/<dv>/pilot_packs/<pack_id>.zip
    Target layout after import:
      artifacts/<dv>/canonical/
      artifacts/<dv>/qc/<qc_run>/
      artifacts/<dv>/models/<model_version>/
      artifacts/<dv>/scoring/<scoring_run>/
      artifacts/<dv>/reports/<report_version>/
      artifacts/<dv>/decisions/

    Verification (if enabled) validates files against pack_manifest.json.
    """
    pack_zip = Path(pack_zip).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    res = ImportPackResult(ok=False, imported_at_utc=utcnow_iso(), pack_zip=str(pack_zip))

    if not pack_zip.exists():
        res.reason = f"pack zip not found: {pack_zip}"
        return asdict(res)

    with tempfile.TemporaryDirectory(prefix="genomeai_import_pack_") as td:
        tmp = Path(td)
        with zipfile.ZipFile(pack_zip, "r") as zf:
            _safe_extract_all(zf, tmp)

        versions_path = tmp / "versions.json"
        if not versions_path.exists():
            res.reason = "versions.json missing in pack"
            return asdict(res)

        try:
            versions = json.loads(versions_path.read_text(encoding="utf-8"))
        except Exception as e:
            res.reason = f"versions.json parse failed: {type(e).__name__}: {e}"
            return asdict(res)

        try:
            normalized_versions = validate_pilot_pack_versions(versions)
        except MigrationCompatibilityError as exc:
            res.reason = str(exc)
            res.mismatches = [exc.as_dict()]
            return asdict(res)

        dv = normalized_versions.get("data_version")
        qc_run = normalized_versions.get("qc_run")
        mv = normalized_versions.get("model_version")
        sr = normalized_versions.get("scoring_run")
        rv = normalized_versions.get("report_version")
        pid = normalized_versions.get("pack_id")

        if not dv or not qc_run or not mv or not sr or not rv:
            res.reason = "versions.json missing required keys (data_version/qc_run/model_version/scoring_run/report_version)"
            return asdict(res)

        res.data_version = str(dv)
        res.qc_run = str(qc_run)
        res.model_version = str(mv)
        res.scoring_run = str(sr)
        res.report_version = str(rv)
        res.pack_id = str(pid) if pid else None

        # Optional verification against pack_manifest.json
        mismatches: list[dict] = []
        manifest_path = tmp / "pack_manifest.json"
        if verify and manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                mismatches.append({"path": "pack_manifest.json", "reason": f"parse_failed: {type(e).__name__}: {e}"})
                manifest = {}

            # validate only files listed in manifest
            for rel, expected in (manifest or {}).items():
                fp = (tmp / rel).resolve()
                if not fp.exists() or not fp.is_file():
                    mismatches.append({"path": rel, "reason": "missing"})
                    continue
                got = _sha256_file(fp)
                if str(got) != str(expected):
                    mismatches.append({"path": rel, "reason": "hash_mismatch", "expected": expected, "got": got})

        res.verified = verify
        res.mismatches = mismatches
        if verify and mismatches:
            res.reason = "pack verification failed"
            return asdict(res)

        base = artifacts_root / str(dv)

        if base.exists() and any(base.iterdir()) and not force:
            res.reason = "destination data_version not empty (use --force)"
            res.dest_base = str(base)
            return asdict(res)

        # If force: keep a backup of existing dv folder
        moved_old: Optional[Path] = None
        if base.exists() and any(base.iterdir()) and force:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            moved_old = base.parent / f"{base.name}_pre_import_{ts}"
            if moved_old.exists():
                shutil.rmtree(moved_old)
            shutil.move(str(base), str(moved_old))

        # Copy layers (pack folders are run-slices; we place them under versioned dirs)
        copied = 0
        copied += _copytree(tmp / "canonical", base / "canonical")
        copied += _copytree(tmp / "qc", base / "qc" / str(qc_run))
        copied += _copytree(tmp / "models", base / "models" / str(mv))
        copied += _copytree(tmp / "scoring", base / "scoring" / str(sr))
        copied += _copytree(tmp / "reports", base / "reports" / str(rv))
        copied += _copytree(tmp / "decisions", base / "decisions")
        copied += _copytree(tmp / "metadata", base / "metadata")

        # Persist import manifest for lineage/compat.
        import_dir = base / "imports" / (res.pack_id or f"import_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
        import_dir.mkdir(parents=True, exist_ok=True)
        import_manifest = {
            "schema": "genomeai.import_pilot_pack.v1",
            "imported_at_utc": res.imported_at_utc,
            "source_pack_zip": str(pack_zip),
            "source_pack_versions": normalized_versions,
            "verification": {
                "enabled": bool(verify),
                "manifest_present": bool(manifest_path.exists()),
                "mismatches": mismatches,
            },
            "dest": {
                "artifacts_root": str(artifacts_root),
                "data_version": str(dv),
                "qc_run": str(qc_run),
                "model_version": str(mv),
                "scoring_run": str(sr),
                "report_version": str(rv),
            },
            "compat": {
                "target_layout": "artifacts/<dv>/{canonical,qc,models,scoring,reports,decisions,metadata}",
                "pack_format": "genomeai.pilot_pack_summary.v1 (versions.json + pack_manifest.json)",
                "pack_schema_version": int(normalized_versions.get("pack_schema_version") or 1),
                "notes": "import tool is backward-compatible with packs missing pack_manifest.json (verification will be skipped)",
            },
            "moved_previous": str(moved_old) if moved_old else None,
            "copied_files": int(copied),
        }
        import_manifest_path = import_dir / "import_manifest.json"
        import_manifest_path.write_text(json.dumps(import_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        res.ok = True
        res.dest_base = str(base)
        res.copied_files = int(copied)
        res.import_manifest_json = str(import_manifest_path)
        return asdict(res)
