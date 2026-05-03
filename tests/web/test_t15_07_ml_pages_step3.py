from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(storage)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts)
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
    os.environ["GENOMEAI_WEB_SECRET"] = "test-secret"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str = "operator", password: str = "operator") -> None:
    resp = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert resp.status_code in (302, 303)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_ml_artifacts(artifacts_root: Path, dv: str) -> None:
    (artifacts_root / dv / "qc" / "qc_demo").mkdir(parents=True, exist_ok=True)

    model_dir = artifacts_root / dv / "runs" / "model_demo" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model_card.md").write_text("# Model Card\n", encoding="utf-8")
    _write_json(
        model_dir / "model_card.json",
        {
            "created_at_utc": "2026-03-15T10:00:00+00:00",
            "model_version": "model_demo",
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "metrics": {"mae": 111.0},
        },
    )
    _write_json(model_dir / "train_summary.json", {"created_at_utc": "2026-03-15T10:00:00+00:00"})
    _write_json(
        artifacts_root / dv / "metadata" / "model_manifest.json",
        {
            "schema": "genomeai.model_manifest.v1",
            "data_version": dv,
            "latest": "model_demo",
            "models": {"model_demo": {"created_at_utc": "2026-03-15T10:00:00+00:00"}},
        },
    )

    scoring_dir = artifacts_root / dv / "runs" / "score_demo" / "scoring"
    exports_dir = scoring_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    for name in ["animal_ranking.xlsx", "recommendations.xlsx", "group_summary.xlsx"]:
        (exports_dir / name).write_text(name, encoding="utf-8")
    (scoring_dir / "scored_latest.csv").write_text("animal_id\nA1\n", encoding="utf-8")
    _write_json(
        scoring_dir / "scoring_summary.json",
        {
            "created_at_utc": "2026-03-15T10:05:00+00:00",
            "model_version": "model_demo",
            "scoring_run": "score_demo",
            "config_version": "ml_pipeline_v1",
            "seed": 42,
            "row_counts": {"n_animals_ranked": 11},
            "status": "OK",
            "outputs": {
                "animal_ranking_xlsx": str((exports_dir / "animal_ranking.xlsx").resolve()),
                "recommendations_xlsx": str((exports_dir / "recommendations.xlsx").resolve()),
                "group_summary_xlsx": str((exports_dir / "group_summary.xlsx").resolve()),
                "scored_latest_csv": str((scoring_dir / "scored_latest.csv").resolve()),
            },
        },
    )
    _write_json(
        artifacts_root / dv / "metadata" / "scoring_manifest.json",
        {
            "schema": "genomeai.scoring_manifest.v1",
            "data_version": dv,
            "latest": "score_demo",
            "scoring_runs": {"score_demo": {"created_at_utc": "2026-03-15T10:05:00+00:00"}},
        },
    )


def test_train_page_renders_core_model_entries_and_canonical_links(client: TestClient) -> None:
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    _seed_ml_artifacts(artifacts_root, "dv_demo")
    _login(client)

    resp = client.get("/train", params={"dv": "dv_demo", "qc": "qc_demo"})
    assert resp.status_code == 200
    assert "cfg=ml_pipeline_v1" in resp.text
    assert "seed=42" in resp.text
    assert "/download?path=artifacts/dv_demo/runs/model_demo/model/model_card.md" in resp.text
    assert "/download?path=artifacts/dv_demo/runs/model_demo/model/train_summary.json" in resp.text


def test_score_page_renders_core_scoring_entries_and_canonical_links(client: TestClient) -> None:
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    _seed_ml_artifacts(artifacts_root, "dv_demo")
    _login(client)

    resp = client.get("/score", params={"dv": "dv_demo", "mv": "model_demo"})
    assert resp.status_code == 200
    assert "model=model_demo" in resp.text
    assert "cfg=ml_pipeline_v1" in resp.text
    assert "ranked=11" in resp.text
    assert "/download?path=artifacts/dv_demo/runs/score_demo/scoring/exports/animal_ranking.xlsx" in resp.text
    assert "/download?path=artifacts/dv_demo/runs/score_demo/scoring/scoring_summary.json" in resp.text
