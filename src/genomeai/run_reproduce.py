from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .versioning import generate_run_id, get_run_root, write_run_manifest, write_checksums, copy_tree_into_run
from core.reporting import run_assistant_report as run_report


@dataclass
class ReproduceResult:
    ok: bool
    data_version: str
    source_run_id: str
    new_run_id: str
    mode: str
    run_root: str
    note: str = ""


def _load_manifest(run_root: Path) -> Dict[str, Any]:
    p = run_root / "run_manifest.json"
    if not p.exists():
        raise FileNotFoundError(f"run_manifest.json not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def reproduce_run(
    *,
    artifacts_root: Path,
    data_version: str,
    run_id: str,
    mode: str = "rerun",
    out_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Reproduce a past run.

    - For step=report and mode=rerun: re-generate report from stored lineage (qc/model/scoring).
    - Otherwise: replay by copying the stored run folder into a new run folder (reproducible snapshot).
    """
    artifacts_root = Path(artifacts_root).resolve()
    src_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=run_id)
    manifest = _load_manifest(src_root)

    step = manifest.get("step", "unknown")
    new_run_id = out_run_id or generate_run_id(prefix=f"reproduce_{step}")
    dst_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=new_run_id)

    note = ""

    if step == "report" and mode == "rerun":
        lineage = manifest.get("lineage", {}) or {}
        qc_run = lineage.get("qc_run")
        model_version = lineage.get("model_version")
        scoring_run = lineage.get("scoring_run")
        if not (qc_run and model_version and scoring_run):
            mode = "replay"
            note = "missing lineage for rerun; falling back to replay"
        else:
            # Re-run report in fallback mode to avoid hallucinations.
            rr = run_report(
                artifacts_root=artifacts_root,
                data_version=data_version,
                qc_run=str(qc_run),
                model_version=str(model_version),
                scoring_run=str(scoring_run),
                mode="fallback",
                report_version=new_run_id,
                make_pdf=True,
            )
            # Ensure run layout is present for the new report (run_report already materializes it in T0-03).
            return {
                "ok": True,
                "data_version": data_version,
                "source_run_id": run_id,
                "new_run_id": new_run_id,
                "mode": "rerun",
                "step": "report",
                "report": rr,
                "run_root": str(dst_root),
                "note": "report rerun completed",
            }

    # Replay mode: copy the whole stored run folder into a new run folder under `replay/`
    copy_tree_into_run(src_dir=src_root, run_root=dst_root, subdir="replay")
    repro_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": "reproduce",
        "data_version": data_version,
        "run_id": new_run_id,
        "created_at": manifest.get("created_at"),
        "status": "DONE",
        "lineage": {
            "source_run_id": run_id,
            "source_step": step,
        },
        "params": {"mode": "replay"},
        "outputs": {
            "run_dir": str(dst_root / "replay"),
        },
        "note": note,
    }
    write_run_manifest(run_root=dst_root, manifest=repro_manifest)
    write_checksums(run_root=dst_root, include_subdirs=["replay"])
    return {
        "ok": True,
        "data_version": data_version,
        "source_run_id": run_id,
        "new_run_id": new_run_id,
        "mode": "replay",
        "step": step,
        "run_root": str(dst_root),
        "note": note,
    }
