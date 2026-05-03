from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.application.ml_artifacts import (
    find_latest_scoring_run,
    list_model_versions,
    list_scoring_runs,
    resolve_model_dir,
    resolve_scoring_dir,
)
from genomeai.dashboard_zootech import load_scoring_outputs
from web_cabinet.utils import list_model_versions as web_list_model_versions
from web_cabinet.utils import list_scoring_runs as web_list_scoring_runs


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_t15_07_model_listing_uses_registry_latest_but_keeps_fallback_dirs(tmp_path: Path) -> None:
    dv = "dv_registry"
    legacy_model = tmp_path / dv / "models" / "model_legacy"
    legacy_model.mkdir(parents=True, exist_ok=True)
    run_model = tmp_path / dv / "runs" / "model_run" / "model"
    run_model.mkdir(parents=True, exist_ok=True)
    _write_json(
        tmp_path / dv / "metadata" / "model_manifest.json",
        {
            "schema": "genomeai.model_manifest.v1",
            "data_version": dv,
            "latest": "model_run",
            "models": {
                "model_manifest_only": {"created_at_utc": "2026-01-01T00:00:00Z"},
                "model_run": {"created_at_utc": "2026-01-02T00:00:00Z"},
            },
        },
    )

    names = list_model_versions(artifacts_root=tmp_path, data_version=dv)
    assert names[:-1] == ["model_legacy", "model_manifest_only"]
    assert names[-1] == "model_run"
    assert web_list_model_versions(tmp_path, dv) == names
    assert resolve_model_dir(artifacts_root=tmp_path, data_version=dv, model_version="model_run") == run_model


def test_t15_07_scoring_registry_prefers_canonical_run_dir_and_latest_manifest(tmp_path: Path) -> None:
    dv = "dv_score_registry"
    legacy_dir = tmp_path / dv / "scoring" / "score_latest"
    run_dir = tmp_path / dv / "runs" / "score_latest" / "scoring"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([{"animal_id": "A_run", "farm_id": "F1", "lactation_no": 1, "y_pred": 100.0}]).to_csv(
        run_dir / "scored_latest.csv", index=False, encoding="utf-8"
    )
    pd.DataFrame([{"animal_id": "A_legacy", "farm_id": "F1", "lactation_no": 1, "y_pred": 50.0}]).to_csv(
        legacy_dir / "scored_latest.csv", index=False, encoding="utf-8"
    )
    pd.DataFrame().to_csv(run_dir / "group_summary.csv", index=False, encoding="utf-8")
    pd.DataFrame().to_csv(legacy_dir / "group_summary.csv", index=False, encoding="utf-8")

    _write_json(
        tmp_path / dv / "metadata" / "scoring_manifest.json",
        {
            "schema": "genomeai.scoring_manifest.v1",
            "data_version": dv,
            "latest": "score_latest",
            "scoring_runs": {
                "score_latest": {"created_at_utc": "2026-01-02T00:00:00Z"},
                "score_manifest_only": {"created_at_utc": "2026-01-01T00:00:00Z"},
            },
        },
    )

    assert find_latest_scoring_run(artifacts_root=tmp_path, data_version=dv) == "score_latest"
    assert resolve_scoring_dir(artifacts_root=tmp_path, data_version=dv, scoring_run="score_latest") == run_dir
    names = list_scoring_runs(artifacts_root=tmp_path, data_version=dv)
    assert names[:-1] == ["score_manifest_only"]
    assert names[-1] == "score_latest"
    assert web_list_scoring_runs(tmp_path, dv) == names

    sr, scored_df, _ = load_scoring_outputs(artifacts_dir=tmp_path, data_version=dv)
    assert sr == "score_latest"
    assert scored_df.iloc[0]["animal_id"] == "A_run"
