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


def test_train_page_exposes_optional_fixed_model_and_config_inputs(client: TestClient) -> None:
    _login(client)

    resp = client.get(
        "/train",
        params={
            "dv": "dv_demo",
            "qc": "qc_demo",
            "model_version": "model_fixed_demo",
            "config": "configs/ml_pipeline_v1.yaml",
        },
    )
    assert resp.status_code == 200
    assert 'name="model_version"' in resp.text
    assert 'value="model_fixed_demo"' in resp.text
    assert 'name="config_path"' in resp.text
    assert 'value="configs/ml_pipeline_v1.yaml"' in resp.text


def test_score_page_exposes_optional_fixed_scoring_run_and_config_inputs(client: TestClient) -> None:
    _login(client)

    resp = client.get(
        "/score",
        params={
            "dv": "dv_demo",
            "mv": "model_demo",
            "scoring_run": "score_fixed_demo",
            "config": "configs/ml_pipeline_v1.yaml",
        },
    )
    assert resp.status_code == 200
    assert 'name="scoring_run"' in resp.text
    assert 'value="score_fixed_demo"' in resp.text
    assert 'name="config_path"' in resp.text
    assert 'value="configs/ml_pipeline_v1.yaml"' in resp.text


def test_train_run_enqueues_job_with_optional_model_version_and_config(client: TestClient) -> None:
    from web_cabinet.db import connect

    _login(client)
    resp = client.post(
        "/train/run",
        data={
            "data_version": "dv_demo",
            "qc_run": "qc_demo",
            "model_version": "model_fixed_demo",
            "config_path": "configs/ml_pipeline_v1.yaml",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    row = conn.execute("SELECT args_json FROM jobs WHERE kind='train' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row is not None
    payload = json.loads(row["args_json"])
    assert payload["argv"] == [
        "train",
        "--data-version",
        "dv_demo",
        "--qc-run",
        "qc_demo",
        "--artifacts",
        os.environ["GENOMEAI_ARTIFACTS_ROOT"],
        "--model-version",
        "model_fixed_demo",
        "--config",
        "configs/ml_pipeline_v1.yaml",
    ]


def test_score_run_enqueues_job_with_optional_scoring_run_and_config(client: TestClient) -> None:
    from web_cabinet.db import connect

    _login(client)
    resp = client.post(
        "/score/run",
        data={
            "data_version": "dv_demo",
            "model_version": "model_demo",
            "scoring_run": "score_fixed_demo",
            "config_path": "configs/ml_pipeline_v1.yaml",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    row = conn.execute("SELECT args_json FROM jobs WHERE kind='score' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row is not None
    payload = json.loads(row["args_json"])
    assert payload["argv"] == [
        "score",
        "--data-version",
        "dv_demo",
        "--model-version",
        "model_demo",
        "--artifacts",
        os.environ["GENOMEAI_ARTIFACTS_ROOT"],
        "--scoring-run",
        "score_fixed_demo",
        "--config",
        "configs/ml_pipeline_v1.yaml",
    ]
