from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from .contracts import load_contracts_dir
from .decision_log import init_decision_log
from .ingest import ingest_dataset
from .pack import build_pilot_pack
from .qc import run_qc
from core.reporting import run_assistant_report as run_report
from .score import run_scoring
from .train import train_productivity_model
from .versioning import generate_run_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SmokeSummary:
    schema: str
    created_at_utc: str
    data_version: str
    qc_run: str
    qc_status: str
    model_version: str
    scoring_run: str
    report_version: str
    pack_id: str
    outputs: Dict[str, str]


def run_smoke(
    artifacts_root: Path,
    contracts_dir: Path,
    data_dir: Path,
    mappings_dir: Path,
    out_version: Optional[str] = None,
) -> Dict[str, object]:
    """One-command minimal check: A1..A6 on synthetic example data."""
    dv = out_version or generate_run_id(prefix="dv_smoke")

    contracts = load_contracts_dir(contracts_dir)

    # Ingest 3 core datasets into one data_version
    for dataset_key, contract_key, file_name, mapping_name in [
        ("farms", "dm_farms", "farms_ext.csv", "farms_example.yaml"),
        ("animals", "dm_animals", "animals_ext.csv", "animals_example.yaml"),
        ("lactations", "dm_lactations", "lactations_ext.csv", "lactations_example.yaml"),
    ]:
        ingest_dataset(
            dataset_key=dataset_key,
            file_path=data_dir / "external" / file_name,
            mapping_path=mappings_dir / mapping_name,
            contract=contracts[contract_key],
            artifacts_root=artifacts_root,
            out_version=dv,
        )

    # QC
    qc = run_qc(
        data_version=dv,
        artifacts_root=artifacts_root,
        contracts_dir=contracts_dir,
        qc_run=None,
    )
    if qc["qc_status"] == "ERROR":
        return {"ok": False, "reason": "QC_ERROR", "qc": qc}
    qr = qc["qc_run"]

    # Train
    tr = train_productivity_model(
        artifacts_root=artifacts_root,
        data_version=dv,
        qc_run=qr,
        model_version=None,
    )
    if not tr.get("ok"):
        return {"ok": False, "reason": "TRAIN_FAILED", "train": tr}
    mv = tr["model_version"]

    # Score
    sc = run_scoring(
        artifacts_root=artifacts_root,
        data_version=dv,
        model_version=mv,
        scoring_run=None,
    )
    if not sc.get("ok"):
        return {"ok": False, "reason": "SCORE_FAILED", "score": sc}
    sr = sc["scoring_run"]

    # Report (fallback only for smoke)
    rep = run_report(
        artifacts_root=artifacts_root,
        data_version=dv,
        qc_run=qr,
        model_version=mv,
        scoring_run=sr,
        mode="fallback",
        report_version=None,
        make_pdf=False,
        llm_model=None,
    )
    if not rep.get("ok"):
        return {"ok": False, "reason": "REPORT_FAILED", "report": rep}
    rv = rep["report_version"]

    # Decisions template
    init_decision_log(
        artifacts_root=artifacts_root,
        data_version=dv,
        scoring_run=sr,
        user="smoke",
        template_from_scoring=True,
    )

    # Pack
    pk = build_pilot_pack(
        artifacts_root=artifacts_root,
        data_version=dv,
        qc_run=qr,
        model_version=mv,
        scoring_run=sr,
        report_version=rv,
        pack_id=None,
    )
    if not pk.get("ok"):
        return {"ok": False, "reason": "PACK_FAILED", "pack": pk}

    summary = SmokeSummary(
        schema="genomeai.smoke_summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=dv,
        qc_run=qr,
        qc_status=qc["qc_status"],
        model_version=mv,
        scoring_run=sr,
        report_version=rv,
        pack_id=pk["pack_id"],
        outputs={
            "pack_dir": pk["pack_dir"],
            "pack_zip": pk["pack_zip"],
            "report_docx": rep["outputs"]["report_docx"],
        },
    )
    return {"ok": True, "summary": asdict(summary)}
