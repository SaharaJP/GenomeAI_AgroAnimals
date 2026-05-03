from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from genomeai.versioning import copy_tree_into_run, get_run_root, write_checksums, write_json, write_run_manifest


def register_qc_run_outputs(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    out_dir: Path,
    summary: Mapping[str, Any],
    kind: str,
) -> dict[str, str]:
    """Register QC/QC2 outputs in metadata and target run layout.

    This keeps legacy artifact directories intact while materializing the target
    run layout under ``artifacts/<data_version>/runs/<qc_run>/<kind>/``.
    """

    if kind not in {"qc", "qc2"}:
        raise ValueError(f"Unsupported QC kind: {kind}")

    artifacts_root = Path(artifacts_root).resolve()
    base = artifacts_root / data_version
    out_dir = Path(out_dir).resolve()
    meta_dir = base / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    outputs = dict(summary.get("outputs") or {})
    manifest_name = f"{kind}_manifest.json"
    manifest_path = meta_dir / manifest_name
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema": f"genomeai.{kind}_manifest.v1",
            "data_version": data_version,
            "runs": {},
        }

    run_record = {
        "created_at_utc": summary.get("created_at_utc") or summary.get("generated_at"),
        "qc_status": summary.get("qc_status"),
        "config_version": summary.get("config_version"),
        "config_path": summary.get("config_path"),
        "qc_summary": str((out_dir / "qc_summary.json").resolve()),
        "qc_report_xlsx": str((out_dir / "qc_report.xlsx").resolve()),
        "qc_issues_csv": str((out_dir / "qc_issues.csv").resolve()),
        "bad_rows_csv": str((out_dir / "bad_rows.csv").resolve()),
        "manifest_json": str((out_dir / "manifest.json").resolve()),
    }
    if kind == "qc2":
        run_record["alerts_auto_csv"] = str((out_dir / "alerts_auto.csv").resolve())
    if outputs.get("bad_rows_detailed_csv"):
        run_record["bad_rows_detailed_csv"] = str(Path(outputs["bad_rows_detailed_csv"]).resolve())

    manifest["runs"][qc_run] = run_record
    manifest["latest"] = qc_run
    write_json(manifest_path, manifest)

    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=qc_run)
    copy_tree_into_run(src_dir=out_dir, run_root=run_root, subdir=kind)
    run_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": kind,
        "data_version": data_version,
        "run_id": qc_run,
        "created_at": summary.get("created_at_utc") or summary.get("generated_at"),
        "status": summary.get("qc_status"),
        "outputs": {
            "legacy_dir": str(out_dir),
            "run_dir": str((run_root / kind).resolve()),
            "qc_report_xlsx": str((out_dir / "qc_report.xlsx").resolve()),
            "qc_issues_csv": str((out_dir / "qc_issues.csv").resolve()),
            "bad_rows_csv": str((out_dir / "bad_rows.csv").resolve()),
            "qc_summary_json": str((out_dir / "qc_summary.json").resolve()),
            "manifest_json": str((out_dir / "manifest.json").resolve()),
        },
        "lineage": {
            "canonical_dir": str((base / "canonical").resolve()),
            "config_path": summary.get("config_path"),
            "config_version": summary.get("config_version"),
        },
    }
    if kind == "qc2":
        run_manifest["outputs"]["alerts_auto_csv"] = str((out_dir / "alerts_auto.csv").resolve())
    if outputs.get("bad_rows_detailed_csv"):
        run_manifest["outputs"]["bad_rows_detailed_csv"] = str(Path(outputs["bad_rows_detailed_csv"]).resolve())
    write_run_manifest(run_root=run_root, manifest=run_manifest)
    write_checksums(run_root=run_root, include_subdirs=[kind])

    return {
        "metadata_manifest_json": str(manifest_path.resolve()),
        "run_manifest_json": str((run_root / "run_manifest.json").resolve()),
        "run_checksums_json": str((run_root / "checksums.json").resolve()),
        "run_dir": str((run_root / kind).resolve()),
    }
