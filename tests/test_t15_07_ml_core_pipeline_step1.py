from __future__ import annotations

import json
from pathlib import Path

from core.application import (
    build_productivity_feature_frame,
    load_ml_pipeline_config,
    run_scoring,
    split_feature_frame_time_aware,
    train_productivity_model,
)
from genomeai.qc import run_qc


def _prep_canonical(tmp_path: Path, data_version: str) -> None:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def test_t15_07_train_writes_config_version_and_registry(tmp_path: Path) -> None:
    dv = "dv_t15_07_train"
    _prep_canonical(tmp_path, dv)
    qc = run_qc(data_version=dv, artifacts_root=tmp_path)

    res = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"], model_version="model_t15_07_a")
    assert res["ok"] is True
    assert res["config_version"] == "ml_pipeline_v1"
    assert res["seed"] == 42

    model_dir = Path(res["model_dir"])
    card = json.loads((model_dir / "model_card.json").read_text(encoding="utf-8"))
    assert card["config_version"] == "ml_pipeline_v1"
    assert card["seed"] == 42
    assert card["run_id"] == "model_t15_07_a"
    assert card["split"]["strategy"] in {"year_holdout", "time_percentile"}

    manifest = json.loads((tmp_path / dv / "metadata" / "model_manifest.json").read_text(encoding="utf-8"))
    assert manifest["latest"] == "model_t15_07_a"
    assert manifest["models"]["model_t15_07_a"]["config_version"] == "ml_pipeline_v1"
    assert manifest["models"]["model_t15_07_a"]["seed"] == 42


def test_t15_07_reproducible_train_and_score_with_same_seed(tmp_path: Path) -> None:
    dv = "dv_t15_07_repro"
    _prep_canonical(tmp_path, dv)
    qc = run_qc(data_version=dv, artifacts_root=tmp_path)

    tr1 = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"], model_version="model_seed_a")
    tr2 = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"], model_version="model_seed_b")
    assert tr1["metrics"] == tr2["metrics"]

    pred1 = (Path(tr1["model_dir"]) / "test_predictions.csv").read_text(encoding="utf-8")
    pred2 = (Path(tr2["model_dir"]) / "test_predictions.csv").read_text(encoding="utf-8")
    assert pred1 == pred2

    sc1 = run_scoring(artifacts_root=tmp_path, data_version=dv, model_version="model_seed_a", scoring_run="score_seed_a")
    sc2 = run_scoring(artifacts_root=tmp_path, data_version=dv, model_version="model_seed_b", scoring_run="score_seed_b")
    assert sc1["row_counts"] == sc2["row_counts"]

    scored1 = (tmp_path / dv / "scoring" / "score_seed_a" / "scored_latest.csv").read_text(encoding="utf-8")
    scored2 = (tmp_path / dv / "scoring" / "score_seed_b" / "scored_latest.csv").read_text(encoding="utf-8")
    assert scored1 == scored2

    scoring_manifest = json.loads((tmp_path / dv / "metadata" / "scoring_manifest.json").read_text(encoding="utf-8"))
    assert scoring_manifest["latest"] == "score_seed_b"
    assert scoring_manifest["scoring_runs"]["score_seed_a"]["config_version"] == "ml_pipeline_v1"


def test_t15_07_time_split_sanity_no_leakage(tmp_path: Path) -> None:
    dv = "dv_t15_07_split"
    _prep_canonical(tmp_path, dv)
    cfg = load_ml_pipeline_config()
    X, y, _limitations = build_productivity_feature_frame(artifacts_root=tmp_path, data_version=dv, cfg_ref=cfg)
    train_idx, test_idx, split_meta = split_feature_frame_time_aware(X, y, cfg)
    assert len(train_idx) > 0
    assert len(test_idx) > 0
    bounds = split_meta["bounds"]
    assert bounds["train_max_key"] <= bounds["test_min_key"]
    if bounds["train_max_year"] is not None and bounds["test_min_year"] is not None:
        assert bounds["train_max_year"] <= bounds["test_min_year"]
