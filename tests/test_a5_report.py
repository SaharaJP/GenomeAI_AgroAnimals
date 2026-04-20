from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from genomeai.report import run_report


def _write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_a5_report_fallback_builds(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    dv = "dv_test"
    qc_run = "qc_test"
    model_version = "model_test"
    scoring_run = "score_test"

    base = artifacts / dv

    # QC summary
    _write_json(
        base / "qc" / qc_run / "qc_summary.json",
        {
            "schema": "genomeai.qc_summary.v1",
            "created_at_utc": "2025-12-23T00:00:00+00:00",
            "data_version": dv,
            "qc_run": qc_run,
            "qc_status": "PASS",
            "datasets_loaded": ["dm_animals", "dm_lactations"],
            "metrics": {"dm_animals.pk_duplicate_rows": 0},
            "outputs": {"qc_report_xlsx": "NA"},
        },
    )

    # Model card
    _write_json(
        base / "models" / model_version / "model_card.json",
        {
            "schema": "genomeai.model_card.v1",
            "created_at_utc": "2025-12-23T00:00:00+00:00",
            "data_version": dv,
            "qc_run": qc_run,
            "qc_status": "PASS",
            "model_version": model_version,
            "task": "baseline_regression",
            "target": "milk_305d_kg",
            "features": {"numeric": ["parity"], "categorical": ["calving_season"]},
            "split": {"strategy": "time_split"},
            "metrics": {"mae": 123.0, "rmse": 456.0},
            "limitations": {"age_at_calving_available": False, "age_at_calving_reason": "no birth_date"},
        },
    )

    # Scoring outputs
    scored_latest = base / "scoring" / scoring_run / "scored_latest.csv"
    scored_latest.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "farm_id": ["F1", "F1", "F2"],
            "animal_id": ["A1", "A2", "A3"],
            "calving_date": ["2025-01-01", "2025-03-01", "2025-02-01"],
            "y_pred": [9000, 8000, 7000],
            "residual": [100, -200, 0],
            "confidence": ["HIGH", "LOW", "MEDIUM"],
            "group_size": [8, 3, 12],
        }
    ).to_csv(scored_latest, index=False, encoding="utf-8")

    rec_xlsx = base / "scoring" / scoring_run / "exports" / "recommendations.xlsx"
    rec_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(rec_xlsx, engine="openpyxl") as xw:
        pd.DataFrame({"farm_id": ["F1"], "animal_id": ["A1"], "y_pred": [9000], "action_reasons": ["top_rank"]}).to_excel(
            xw, index=False, sheet_name="priority"
        )
        pd.DataFrame({"farm_id": ["F1"], "animal_id": ["A2"], "y_pred": [8000], "action_reasons": ["low_conf"]}).to_excel(
            xw, index=False, sheet_name="observe"
        )
        pd.DataFrame({"farm_id": ["F2"], "animal_id": ["A3"], "y_pred": [7000], "action_reasons": ["low_residual"]}).to_excel(
            xw, index=False, sheet_name="cull_candidates"
        )

    _write_json(
        base / "scoring" / scoring_run / "scoring_summary.json",
        {
            "schema": "genomeai.scoring_summary.v1",
            "created_at_utc": "2025-12-23T00:00:00+00:00",
            "data_version": dv,
            "model_version": model_version,
            "scoring_run": scoring_run,
            "inputs": {"canonical_dir": "NA", "canonical_hash": "NA", "model_card": "NA"},
            "outputs": {
                "recommendations_xlsx": str(rec_xlsx),
                "scored_latest_csv": str(scored_latest),
            },
            "row_counts": {"n_animals_ranked": 3, "n_priority": 1, "n_observe": 1, "n_cull_candidates": 1},
            "status": "OK",
        },
    )

    res = run_report(
        artifacts_root=artifacts,
        data_version=dv,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode="fallback",
        make_pdf=False,
    )

    assert res["ok"] is True
    assert Path(res["outputs"]["report_docx"]).exists()
    assert Path(res["fact_pack"]).exists()


def test_a5_report_llm_falls_back_without_key(tmp_path: Path, monkeypatch):
    # Minimal: reuse fallback builder and just ensure llm_used False when no key.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    artifacts = tmp_path / "artifacts"
    dv = "dv_test"
    qc_run = "qc_test"
    model_version = "model_test"
    scoring_run = "score_test"
    base = artifacts / dv

    _write_json(base / "qc" / qc_run / "qc_summary.json", {"qc_status": "PASS"})
    _write_json(base / "models" / model_version / "model_card.json", {"metrics": {"mae": 1, "rmse": 2}, "features": {}, "limitations": {}})
    scored_latest = base / "scoring" / scoring_run / "scored_latest.csv"
    scored_latest.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"y_pred": [1]}).to_csv(scored_latest, index=False)
    rec_xlsx = base / "scoring" / scoring_run / "exports" / "recommendations.xlsx"
    rec_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(rec_xlsx, engine="openpyxl") as xw:
        pd.DataFrame({"animal_id": ["A1"]}).to_excel(xw, index=False, sheet_name="priority")
        pd.DataFrame({"animal_id": []}).to_excel(xw, index=False, sheet_name="observe")
        pd.DataFrame({"animal_id": []}).to_excel(xw, index=False, sheet_name="cull_candidates")
    _write_json(
        base / "scoring" / scoring_run / "scoring_summary.json",
        {"outputs": {"recommendations_xlsx": str(rec_xlsx), "scored_latest_csv": str(scored_latest)}, "row_counts": {}},
    )

    res = run_report(
        artifacts_root=artifacts,
        data_version=dv,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode="llm",
        make_pdf=False,
    )
    assert res["ok"] is True
    assert res["llm_used"] is False
    assert Path(res["outputs"]["report_docx"]).exists()
