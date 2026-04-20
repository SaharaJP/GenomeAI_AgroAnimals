from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from genomeai.pack import build_pilot_pack
from genomeai.regular_reports import build_fact_pack_regular
from genomeai.report import run_report


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prepare_qc(artifacts: Path, dv: str, qc_run: str) -> None:
    _write_json(
        artifacts / dv / "qc" / qc_run / "qc_summary.json",
        {
            "schema": "genomeai.qc_summary.v1",
            "created_at_utc": "2026-03-15T10:00:00+00:00",
            "data_version": dv,
            "qc_run": qc_run,
            "qc_status": "PASS",
            "datasets_loaded": ["dm_animals", "dm_lactations"],
            "metrics": {"dm_animals.row_count": 3},
            "outputs": {"qc_report_xlsx": "NA"},
        },
    )


def _prepare_canonical_ml_only(artifacts: Path, dv: str, mv: str, sr: str, qc_run: str) -> tuple[Path, Path]:
    model_dir = artifacts / dv / "runs" / mv / "model"
    score_dir = artifacts / dv / "runs" / sr / "scoring"
    exports_dir = score_dir / "exports"
    model_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        model_dir / "model_card.json",
        {
            "schema": "genomeai.model_card.v1",
            "created_at_utc": "2026-03-15T10:00:00+00:00",
            "run_id": mv,
            "data_version": dv,
            "qc_run": qc_run,
            "qc_status": "PASS",
            "model_version": mv,
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "task": "baseline_regression",
            "target": "milk_305d_kg",
            "features": {"numeric": ["parity"], "categorical": ["farm_id"]},
            "split": {"strategy": "time_split"},
            "metrics": {"mae": 111.0, "rmse": 222.0},
            "limitations": {"age_at_calving_available": False},
        },
    )
    _write_json(
        model_dir / "train_summary.json",
        {
            "schema": "genomeai.train_summary.v1",
            "created_at_utc": "2026-03-15T10:00:00+00:00",
            "data_version": dv,
            "qc_run": qc_run,
            "qc_status": "PASS",
            "model_version": mv,
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "target": "milk_305d_kg",
            "features": {"numeric": ["parity"], "categorical": ["farm_id"]},
            "split": {"strategy": "time_split"},
            "metrics": {"mae": 111.0, "rmse": 222.0},
            "outputs": {},
            "limitations": {"age_at_calving_available": False},
        },
    )
    (model_dir / "model_card.md").write_text("# model\n", encoding="utf-8")
    (model_dir / "model.joblib").write_bytes(b"not-a-real-model")

    scored_latest = score_dir / "scored_latest.csv"
    pd.DataFrame(
        {
            "farm_id": ["F1", "F1", "F2"],
            "animal_id": ["A1", "A2", "A3"],
            "calving_date": ["2025-01-01", "2025-02-01", "2025-03-01"],
            "y_pred": [9000, 8500, 7000],
            "residual": [100, -50, 0],
            "confidence": ["HIGH", "MEDIUM", "LOW"],
            "group_size": [8, 8, 2],
            "explain_top_factors_text": ["parity=2", "farm_id=F1", "insufficient_explainability_data"],
            "explain_counterfactuals_text": ["+50 milk", "no_simple_counterfactual", "no_simple_counterfactual"],
        }
    ).to_csv(scored_latest, index=False, encoding="utf-8")

    rec_xlsx = exports_dir / "recommendations.xlsx"
    with pd.ExcelWriter(rec_xlsx, engine="openpyxl") as xw:
        pd.DataFrame({"farm_id": ["F1"], "animal_id": ["A1"], "y_pred": [9000], "action_reasons": ["top_rank"]}).to_excel(
            xw, index=False, sheet_name="priority"
        )
        pd.DataFrame({"farm_id": ["F1"], "animal_id": ["A2"], "y_pred": [8500], "action_reasons": ["observe"]}).to_excel(
            xw, index=False, sheet_name="observe"
        )
        pd.DataFrame({"farm_id": ["F2"], "animal_id": ["A3"], "y_pred": [7000], "action_reasons": ["cull"]}).to_excel(
            xw, index=False, sheet_name="cull_candidates"
        )

    _write_json(
        score_dir / "scoring_summary.json",
        {
            "schema": "genomeai.scoring_summary.v1",
            "created_at_utc": "2026-03-15T10:10:00+00:00",
            "data_version": dv,
            "model_version": mv,
            "scoring_run": sr,
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "inputs": {
                "model_dir": str(model_dir),
                "model_card": str(model_dir / "model_card.json"),
            },
            "outputs": {
                # intentionally point to missing legacy layout; report must fall back to canonical run layout
                "recommendations_xlsx": str(artifacts / dv / "scoring" / sr / "exports" / "recommendations.xlsx"),
                "scored_latest_csv": str(artifacts / dv / "scoring" / sr / "scored_latest.csv"),
            },
            "row_counts": {"n_animals_ranked": 3, "n_priority": 1, "n_observe": 1, "n_cull_candidates": 1},
            "status": "OK",
        },
    )
    return model_dir, score_dir


def test_t15_07_report_builds_from_canonical_ml_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_demo"
    qc_run = "qc_demo"
    mv = "model_demo"
    sr = "score_demo"

    _prepare_qc(artifacts, dv, qc_run)
    model_dir, score_dir = _prepare_canonical_ml_only(artifacts, dv, mv, sr, qc_run)

    res = run_report(
        artifacts_root=artifacts,
        data_version=dv,
        qc_run=qc_run,
        model_version=mv,
        scoring_run=sr,
        mode="fallback",
        make_pdf=False,
    )

    assert res["ok"] is True
    fact_pack = json.loads(Path(res["fact_pack"]).read_text(encoding="utf-8"))
    assert fact_pack["ml"]["model_card_path"] == str((model_dir / "model_card.json").resolve())
    assert fact_pack["scoring"]["outputs"]["recommendations_xlsx"] == str((score_dir / "exports" / "recommendations.xlsx").resolve())
    assert fact_pack["scoring"]["outputs"]["scored_latest_csv"] == str((score_dir / "scored_latest.csv").resolve())
    assert len(fact_pack["top_lists"]["priority"]) == 1



def test_t15_07_pack_uses_canonical_ml_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_demo"
    qc_run = "qc_demo"
    mv = "model_demo"
    sr = "score_demo"
    rv = "report_demo"

    _prepare_qc(artifacts, dv, qc_run)
    model_dir, score_dir = _prepare_canonical_ml_only(artifacts, dv, mv, sr, qc_run)
    canonical_dir = artifacts / dv / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    (canonical_dir / "dm_animals.csv").write_text("animal_id\nA1\n", encoding="utf-8")
    report_dir = artifacts / dv / "reports" / rv
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.md").write_text("demo\n", encoding="utf-8")

    pack = build_pilot_pack(
        artifacts_root=artifacts,
        data_version=dv,
        qc_run=qc_run,
        model_version=mv,
        scoring_run=sr,
        report_version=rv,
        pack_id="pilot_demo",
    )

    assert pack["ok"] is True
    assert pack["summary"]["inputs"]["model_dir"] == str(model_dir.resolve())
    assert pack["summary"]["inputs"]["scoring_dir"] == str(score_dir.resolve())
    with zipfile.ZipFile(pack["pack_zip"], "r") as zf:
        names = set(zf.namelist())
        assert "models/model_card.json" in names
        assert "scoring/scoring_summary.json" in names
        assert "decisions/decision_log.csv" in names



def test_t15_07_regular_reports_find_latest_model_from_canonical_run_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_demo"
    mv = "model_demo"
    model_dir = artifacts / dv / "runs" / mv / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    _write_json(model_dir / "model_card.json", {"created_at_utc": "2026-03-15T10:00:00+00:00"})

    fp = build_fact_pack_regular(artifacts_root=artifacts, data_version=dv, asof_date="2026-03-15", period="daily")
    assert ((fp.get("versions") or {}).get("model_version")) == mv
