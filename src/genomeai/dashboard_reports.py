from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from core.common.time import utc_isoformat_z

from .versioning import generate_run_id, ensure_run_dir, write_run_manifest, write_checksums, write_json


def load_dashboard_report_manifest(*, artifacts_root: Path, data_version: str) -> Dict[str, Any]:
    """Load per-data_version dashboard report manifest.

    This manifest is written by save_dashboard_snapshot_as_report().
    Returns an empty structure if missing or corrupted.
    """

    artifacts_root = Path(artifacts_root)
    dv = str(data_version)
    manifest_path = artifacts_root / dv / "metadata" / "dashboard_report_manifest.json"
    if not manifest_path.exists():
        return {
            "schema": "genomeai.dashboard_report_manifest.v1",
            "data_version": dv,
            "reports": {},
            "latest": None,
        }
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest is not a dict")
        manifest.setdefault("schema", "genomeai.dashboard_report_manifest.v1")
        manifest.setdefault("data_version", dv)
        manifest.setdefault("reports", {})
        manifest.setdefault("latest", None)
        return manifest
    except Exception as e:
        return {
            "schema": "genomeai.dashboard_report_manifest.v1",
            "data_version": dv,
            "reports": {},
            "latest": None,
            "error": f"failed_to_read_manifest: {e}",
        }


def list_dashboard_reports(
    *,
    artifacts_root: Path,
    data_version: str,
    dashboard_kind: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """List saved dashboard reports (report_version).

    The function is filesystem-only (no heavy computation). Intended for web-cabinet.
    """

    manifest = load_dashboard_report_manifest(artifacts_root=artifacts_root, data_version=data_version)
    reports: Dict[str, Any] = manifest.get("reports") or {}

    items = []
    for rep_ver, meta in reports.items():
        if not isinstance(meta, dict):
            continue
        kind = str(meta.get("dashboard_kind") or "")
        if dashboard_kind and kind != dashboard_kind:
            continue
        items.append(
            {
                "report_version": rep_ver,
                "created_at_utc": meta.get("created_at_utc"),
                "dashboard_run_id": meta.get("dashboard_run_id"),
                "dashboard_kind": kind,
                "summary": meta.get("summary"),
                "exports_dir": meta.get("exports_dir"),
            }
        )

    # Newest first (created_at_utc is ISO)
    def _key(x: Dict[str, Any]) -> str:
        return str(x.get("created_at_utc") or "")

    items = sorted(items, key=_key, reverse=True)
    if limit and len(items) > limit:
        items = items[: int(limit)]

    return {
        "ok": True,
        "schema": "genomeai.dashboard_report_list.v1",
        "data_version": str(data_version),
        "dashboard_kind": dashboard_kind,
        "count": len(items),
        "latest": manifest.get("latest"),
        "items": items,
        "manifest_error": manifest.get("error"),
    }


def read_dashboard_report_summary(*, summary_path: Path) -> Dict[str, Any]:
    """Read dashboard_report_summary.json by explicit path (best effort)."""

    p = Path(summary_path)
    if not p.exists():
        return {"ok": False, "reason": f"summary not found: {p}"}
    try:
        import json

        return {"ok": True, "summary": json.loads(p.read_text(encoding="utf-8")), "path": str(p)}
    except Exception as e:
        return {"ok": False, "reason": f"failed to read summary: {e}", "path": str(p)}


def list_dashboard_report_exports(*, exports_dir: Path, max_files: int = 200) -> Dict[str, Any]:
    """List files inside exports_dir (recursive, limited).

    This is safe for web-cabinet: it only reads filesystem metadata.
    """
    exports_dir = Path(exports_dir)
    if not exports_dir.exists():
        return {"ok": False, "reason": f"exports_dir not found: {exports_dir}"}
    files = []
    try:
        for p in sorted(exports_dir.rglob("*")):
            if p.is_file():
                files.append(
                    {
                        "relpath": str(p.relative_to(exports_dir)),
                        "name": p.name,
                        "size_bytes": p.stat().st_size,
                        "path": str(p),
                    }
                )
                if max_files and len(files) >= int(max_files):
                    break
    except Exception as e:
        return {"ok": False, "reason": f"failed to list exports: {e}"}
    return {"ok": True, "exports_dir": str(exports_dir), "count": len(files), "files": files}


@dataclass
class DashboardReportSummary:
    schema: str
    created_at_utc: str
    data_version: str
    report_version: str
    dashboard_run_id: str
    dashboard_kind: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    lineage: Dict[str, Any]


def _utc_now_iso() -> str:
    return utc_isoformat_z()


def _copy_dir(src: Path, dst: Path) -> int:
    """Copy directory tree (best effort). Returns number of files copied."""
    src = Path(src)
    dst = Path(dst)
    if not src.exists() or not src.is_dir():
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            n += 1
    return n


def save_dashboard_snapshot_as_report(
    *,
    artifacts_root: Path,
    data_version: str,
    dashboard_run_id: str,
    dashboard_kind: str = "director_summary",
    report_version: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a dashboard snapshot as a versioned report.

    Layout:
      artifacts/<dv>/reports/<report_version>/dashboard/<dashboard_kind>/...
    Also materializes Target run folder:
      artifacts/<dv>/runs/<report_version>/dashboard_report/...
    """

    artifacts_root = Path(artifacts_root)
    dv = str(data_version)
    dash_run = str(dashboard_run_id)
    rep_ver = report_version or generate_run_id(prefix="reportdash")

    dash_dir = artifacts_root / dv / "runs" / dash_run / "dashboards" / dashboard_kind
    if not dash_dir.exists():
        return {
            "ok": False,
            "reason": f"dashboard snapshot not found: {dash_dir}. "
                      f"Expected artifacts/<dv>/runs/<dash_run>/dashboards/{dashboard_kind}/",
        }

    # Legacy (human-facing) report directory
    out_dir = artifacts_root / dv / "reports" / rep_ver / "dashboard" / dashboard_kind
    exports_dir = out_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    copied = _copy_dir(dash_dir, exports_dir)
    if copied == 0:
        return {
            "ok": False,
            "reason": f"dashboard snapshot dir is empty: {dash_dir}",
        }

    # Read dashboard run manifest if present (for lineage)
    dash_manifest_path = artifacts_root / dv / "runs" / dash_run / "run_manifest.json"
    dash_manifest: Dict[str, Any] = {}
    if dash_manifest_path.exists():
        try:
            import json

            dash_manifest = json.loads(dash_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            dash_manifest = {}

    summary = DashboardReportSummary(
        schema="genomeai.dashboard_report_summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=dv,
        report_version=rep_ver,
        dashboard_run_id=dash_run,
        dashboard_kind=dashboard_kind,
        inputs={
            "dashboard_dir": str(dash_dir.resolve()),
            "notes": notes or "",
        },
        outputs={
            "exports_dir": str(exports_dir.resolve()),
            "files_copied": copied,
        },
        lineage={
            "dashboard_run_manifest": str(dash_manifest_path.resolve()) if dash_manifest_path.exists() else None,
            "dashboard_lineage": dash_manifest.get("lineage"),
            "dashboard_inputs": dash_manifest.get("inputs"),
        },
    )

    write_json(out_dir / "dashboard_report_summary.json", asdict(summary))
    write_json(out_dir / "dashboard_report_manifest.json", asdict(summary))

    # Update per-data_version metadata manifest
    meta_dir = artifacts_root / dv / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = meta_dir / "dashboard_report_manifest.json"
    if manifest_path.exists():
        try:
            import json

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    else:
        manifest = {"schema": "genomeai.dashboard_report_manifest.v1", "data_version": dv, "reports": {}, "latest": None}

    manifest.setdefault("reports", {})
    manifest["reports"][rep_ver] = {
        "created_at_utc": summary.created_at_utc,
        "dashboard_run_id": dash_run,
        "dashboard_kind": dashboard_kind,
        "summary": str((out_dir / "dashboard_report_summary.json").resolve()),
        "exports_dir": str(exports_dir.resolve()),
    }
    manifest["latest"] = rep_ver
    write_json(manifest_path, manifest)

    # Target run layout
    run_root = ensure_run_dir(artifacts_root, dv, rep_ver)
    run_dst = run_root / "dashboard_report" / "dashboard" / dashboard_kind
    _copy_dir(out_dir, run_root / "dashboard_report")

    run_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": "dashboard_report",
        "data_version": dv,
        "run_id": rep_ver,
        "created_at": summary.created_at_utc,
        "status": "DONE",
        "outputs": {
            "legacy_dir": str(out_dir.resolve()),
            "run_dir": str((run_root / "dashboard_report").resolve()),
            "exports_dir": str(exports_dir.resolve()),
        },
        "lineage": {
            "dashboard_run_id": dash_run,
            "dashboard_kind": dashboard_kind,
        },
        "params": {
            "notes": notes or "",
        },
    }
    write_run_manifest(run_root=run_root, manifest=run_manifest)
    write_checksums(run_root=run_root, include_subdirs=["dashboard_report"])

    return {
        "ok": True,
        "data_version": dv,
        "dashboard_run_id": dash_run,
        "report_version": rep_ver,
        "report_dir": str(out_dir.resolve()),
        "exports_dir": str(exports_dir.resolve()),
        "files_copied": copied,
    }
