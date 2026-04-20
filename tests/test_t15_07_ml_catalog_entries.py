from __future__ import annotations

import json
from pathlib import Path

from core.application.ml_artifacts import list_model_entries, list_scoring_entries


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_t15_07_model_entries_read_metadata_and_canonical_relpaths(tmp_path: Path) -> None:
    dv = "dv_ml_entries"
    model_dir = tmp_path / dv / "runs" / "model_demo" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        model_dir / "model_card.json",
        {
            "model_version": "model_demo",
            "created_at_utc": "2026-03-15T10:00:00+00:00",
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "metrics": {"mae": 123.456},
        },
    )
    (model_dir / "model_card.md").write_text("# demo\n", encoding="utf-8")
    _write_json(model_dir / "train_summary.json", {"created_at_utc": "2026-03-15T10:00:00+00:00"})
    _write_json(
        tmp_path / dv / "metadata" / "model_manifest.json",
        {
            "schema": "genomeai.model_manifest.v1",
            "data_version": dv,
            "latest": "model_demo",
            "models": {"model_demo": {"created_at_utc": "2026-03-15T10:00:00+00:00"}},
        },
    )

    rows = list_model_entries(artifacts_root=tmp_path, data_version=dv)
    assert len(rows) == 1
    row = rows[0]
    assert row["model_version"] == "model_demo"
    assert row["is_latest"] is True
    assert row["config_version"] == "ml_pipeline_v1"
    assert row["seed"] == 42
    assert row["metrics"]["mae"] == 123.456
    assert row["model_card_md_relpath"] == f"{dv}/runs/model_demo/model/model_card.md"
    assert row["train_summary_relpath"] == f"{dv}/runs/model_demo/model/train_summary.json"


def test_t15_07_scoring_entries_prefer_summary_outputs_and_canonical_relpaths(tmp_path: Path) -> None:
    dv = "dv_ml_scores"
    scoring_dir = tmp_path / dv / "runs" / "score_demo" / "scoring"
    exports_dir = scoring_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    for name in ["animal_ranking.xlsx", "group_summary.xlsx", "recommendations.xlsx"]:
        (exports_dir / name).write_text(name, encoding="utf-8")
    (scoring_dir / "scored_latest.csv").write_text("animal_id\nA1\n", encoding="utf-8")
    (scoring_dir / "productivity_explanations.csv").write_text("row_id\n1\n", encoding="utf-8")
    _write_json(
        scoring_dir / "scoring_summary.json",
        {
            "scoring_run": "score_demo",
            "created_at_utc": "2026-03-15T10:05:00+00:00",
            "model_version": "model_demo",
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "row_counts": {"n_animals_ranked": 11},
            "outputs": {
                "animal_ranking_xlsx": str((exports_dir / "animal_ranking.xlsx").resolve()),
                "group_summary_xlsx": str((exports_dir / "group_summary.xlsx").resolve()),
                "recommendations_xlsx": str((exports_dir / "recommendations.xlsx").resolve()),
                "scored_latest_csv": str((scoring_dir / "scored_latest.csv").resolve()),
                "explanations_csv": str((scoring_dir / "productivity_explanations.csv").resolve()),
            },
            "status": "OK",
        },
    )
    _write_json(
        tmp_path / dv / "metadata" / "scoring_manifest.json",
        {
            "schema": "genomeai.scoring_manifest.v1",
            "data_version": dv,
            "latest": "score_demo",
            "scoring_runs": {"score_demo": {"created_at_utc": "2026-03-15T10:05:00+00:00"}},
        },
    )

    rows = list_scoring_entries(artifacts_root=tmp_path, data_version=dv)
    assert len(rows) == 1
    row = rows[0]
    assert row["scoring_run"] == "score_demo"
    assert row["is_latest"] is True
    assert row["model_version"] == "model_demo"
    assert row["config_version"] == "ml_pipeline_v1"
    assert row["row_counts"]["n_animals_ranked"] == 11
    assert row["animal_ranking_relpath"] == f"{dv}/runs/score_demo/scoring/exports/animal_ranking.xlsx"
    assert row["recommendations_relpath"] == f"{dv}/runs/score_demo/scoring/exports/recommendations.xlsx"
    assert row["scoring_summary_relpath"] == f"{dv}/runs/score_demo/scoring/scoring_summary.json"
