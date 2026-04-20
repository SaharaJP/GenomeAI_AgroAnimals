from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.reporting import (
    build_assistant_fact_pack,
    build_regular_fact_pack,
    persist_fact_pack_bundle,
    write_markdown_report_bundle,
)
from genomeai.regular_reports import build_fact_pack_regular
from genomeai.report import build_fact_pack


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_t15_08_legacy_fact_pack_exports_are_core_wrappers() -> None:
    assert build_fact_pack is build_assistant_fact_pack
    assert build_fact_pack_regular is build_regular_fact_pack


def test_t15_08_core_assistant_fact_pack_keeps_key_facts_and_traceability(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_t15_08_assistant"
    qc_run = "qc_t15_08_assistant"
    model_version = "model_t15_08_assistant"
    scoring_run = "score_t15_08_assistant"
    base = artifacts / dv

    _write_json(
        base / "qc" / qc_run / "qc_summary.json",
        {
            "qc_status": "PASS",
            "datasets_loaded": ["dm_animals", "dm_lactations"],
            "metrics": {"dm_animals.pk_duplicate_rows": 0},
            "outputs": {"qc_report_xlsx": "NA"},
        },
    )
    _write_json(
        base / "models" / model_version / "model_card.json",
        {
            "task": "baseline_regression",
            "target": "milk_305d_kg",
            "features": {"numeric": ["parity"]},
            "split": {"strategy": "time_split"},
            "metrics": {"mae": 123.0, "rmse": 456.0},
            "limitations": {"age_at_calving_available": False},
        },
    )
    scored_latest = base / "scoring" / scoring_run / "scored_latest.csv"
    scored_latest.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "farm_id": ["F1", "F1"],
            "animal_id": ["A1", "A2"],
            "calving_date": ["2025-01-01", "2025-03-01"],
            "y_pred": [9000, 8000],
            "residual": [100, -200],
            "confidence": ["HIGH", "LOW"],
        }
    ).to_csv(scored_latest, index=False, encoding="utf-8")
    rec_xlsx = base / "scoring" / scoring_run / "exports" / "recommendations.xlsx"
    rec_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(rec_xlsx, engine="openpyxl") as writer:
        pd.DataFrame({"animal_id": ["A1"], "y_pred": [9000]}).to_excel(writer, index=False, sheet_name="priority")
        pd.DataFrame({"animal_id": ["A2"], "y_pred": [8000]}).to_excel(writer, index=False, sheet_name="observe")
        pd.DataFrame({"animal_id": [], "y_pred": []}).to_excel(writer, index=False, sheet_name="cull_candidates")
    _write_json(
        base / "scoring" / scoring_run / "scoring_summary.json",
        {
            "model_version": model_version,
            "scoring_run": scoring_run,
            "inputs": {"canonical_dir": "NA"},
            "outputs": {
                "recommendations_xlsx": str(rec_xlsx),
                "scored_latest_csv": str(scored_latest),
            },
            "row_counts": {"n_animals_ranked": 2, "n_priority": 1, "n_observe": 1},
            "status": "OK",
        },
    )

    fp = build_assistant_fact_pack(
        artifacts_root=artifacts,
        data_version=dv,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
    )

    assert fp["versions"] == {
        "data_version": dv,
        "qc_run": qc_run,
        "model_version": model_version,
        "scoring_run": scoring_run,
    }
    assert fp["qc"]["qc_status"] == "PASS"
    assert fp["qc"]["qc_summary_path"] == str((base / "qc" / qc_run / "qc_summary.json").resolve())
    assert fp["ml"]["metrics"]["mae"] == 123.0
    assert fp["scoring"]["outputs"]["recommendations_xlsx"] == str(rec_xlsx.resolve())
    assert fp["scoring"]["outputs"]["scored_latest_csv"] == str(scored_latest.resolve())
    assert len(fp["top_lists"]["priority"]) == 1
    assert fp["temporal"]["calving_season_counts"]["winter"] == 1
    assert fp["temporal"]["calving_season_counts"]["spring"] == 1


def test_t15_08_core_regular_fact_pack_and_markdown_bundle(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_t15_08_regular"
    kpi_dir = artifacts / dv / "runs" / "kpi_t15_08" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    _write_json(kpi_dir / "kpi_summary.json", {"run_id": "kpi_t15_08", "kpi_count": 1, "alert_count": 1, "currency": "RUB"})
    pd.DataFrame([{"kpi_id": "milk_total_kg_7d", "value": 123.4, "unit": "kg"}]).to_csv(kpi_dir / "kpi_wide.csv", index=False)
    pd.DataFrame([{"alert_id": "AL1", "severity": "high"}]).to_csv(kpi_dir / "kpi_alerts.csv", index=False)

    fp = build_regular_fact_pack(
        artifacts_root=artifacts,
        data_version=dv,
        asof_date="2026-03-15",
        period="daily",
    )
    assert fp["schema"] == "genomeai.fact_pack.regular.v1"
    assert fp["versions"]["data_version"] == dv
    assert fp["modules"]["kpi"]["available"] is True
    assert fp["modules"]["kpi"]["kpi_count"] == 1
    assert fp["modules"]["kpi"]["alert_count"] == 1
    assert fp["modules"]["kpi"]["sources"]["kpi_wide"] == str((kpi_dir / "kpi_wide.csv").resolve())

    out_dir = artifacts / dv / "reports_regular" / "report_t15_08"
    fp.setdefault("versions", {})["report_version"] = "report_t15_08"
    persisted = persist_fact_pack_bundle(out_dir=out_dir, fact_pack=fp, report_version="report_t15_08")
    persisted_payload = json.loads((out_dir / "fact_pack.json").read_text(encoding="utf-8"))
    assert persisted["fact_pack_hash"] == persisted_payload["fact_pack_hash"]
    assert persisted_payload["versions"]["report_version"] == "report_t15_08"

    outputs = write_markdown_report_bundle(
        exports_dir=out_dir / "exports",
        markdown_by_audience={
            "director": "# Demo director\n\nmetric=1\n",
            "ops": "# Demo ops\n\nmetric=1\n",
        },
        pdf_titles={"director": "Director", "ops": "Ops"},
    )
    assert Path(outputs["director_md"]).exists()
    assert Path(outputs["director_html"]).exists()
    assert outputs["director_pdf"] == "NA" or Path(outputs["director_pdf"]).exists()
