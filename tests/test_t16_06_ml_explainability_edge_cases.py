from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd

from genomeai.explainability_v1 import explain_regression_row, safe_abs_correlation
from genomeai.qc import run_qc
from genomeai.score import run_scoring
from genomeai.train import train_productivity_model


class _FailingPredictPipe:
    def predict(self, df: pd.DataFrame):
        raise ValueError("predict unavailable for empty-like edge case")


def _prep_tiny_canonical(tmp_path: Path, data_version: str) -> None:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def test_safe_abs_correlation_handles_tiny_constant_and_empty_inputs_without_runtime_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert safe_abs_correlation([], []) == 0.0
        assert safe_abs_correlation(pd.Series([1.0]), pd.Series([2.0])) == 0.0
        assert safe_abs_correlation(pd.Series([5.0, 5.0, 5.0]), pd.Series([1.0, 2.0, 3.0])) == 0.0
        corr = safe_abs_correlation(pd.Series([1.0, 2.0, 3.0]), pd.Series([2.0, 4.0, 6.0]))
    assert abs(corr - 1.0) < 1e-12


def test_explain_regression_row_handles_empty_like_input_with_compatible_defaults() -> None:
    row = pd.Series({"animal_id": "A0001", "y_pred": 9100.0}, name="missing_row")
    profile = {
        "features": ["milk_kg", "fat_pct"],
        "feature_importances": {"milk_kg": 0.8, "fat_pct": 0.2},
        "baseline_median": {"milk_kg": 27.0, "fat_pct": 4.0},
        "baseline_scale": {"milk_kg": 5.0, "fat_pct": 0.2},
        "feature_rules": {"milk_kg": "higher_increases_prediction", "fat_pct": "higher_increases_prediction"},
        "top_k": 2,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = explain_regression_row(
            row=row,
            score_df=pd.DataFrame(),
            pipe=_FailingPredictPipe(),
            profile=profile,
            cfg={"productivity_explainability": {"top_k": 2}},
        )
    assert result["top_factors"] == []
    assert result["counterfactuals"] == []
    assert result["top_factors_text"] == "insufficient_explainability_data"
    assert result["counterfactuals_text"] == "no_simple_counterfactual"
    assert result["base_prediction"] == 9100.0


def test_tiny_train_and_score_do_not_emit_numpy_runtime_warning_and_keep_explainability_artifacts(tmp_path: Path) -> None:
    data_version = "dv_t16_06_tiny"
    _prep_tiny_canonical(tmp_path, data_version)
    qc = run_qc(data_version=data_version, artifacts_root=tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        train_res = train_productivity_model(artifacts_root=tmp_path, data_version=data_version, qc_run=qc["qc_run"])
        score_res = run_scoring(artifacts_root=tmp_path, data_version=data_version, model_version=train_res["model_version"])

    assert train_res["ok"] is True
    assert score_res["ok"] is True

    profile_path = Path(train_res["outputs"]["explainability_profile_json"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["schema"] == "genomeai.explainability_profile.v1"
    assert profile["task_kind"] == "regression"
    assert profile["features"]
    assert set(profile["feature_importances"]) == set(profile["features"])

    scored = pd.read_csv(Path(score_res["outputs"]["scored_latest_csv"]))
    assert "explain_top_factors_text" in scored.columns
    assert "explain_counterfactuals_text" in scored.columns
    assert len(scored) >= 1
