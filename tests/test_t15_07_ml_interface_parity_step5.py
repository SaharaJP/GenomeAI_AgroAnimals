from __future__ import annotations

from pathlib import Path

from core.application import (
    build_model_surface_snapshot,
    build_score_job_request,
    build_scoring_surface_snapshot,
    build_train_job_request,
    load_model_registry,
    load_scoring_registry,
    run_pipeline_job,
)
from genomeai.cli import main as cli_main
from genomeai.qc import run_qc
from streamlit_app.pipeline_jobs import (
    build_streamlit_score_job_request,
    build_streamlit_train_job_request,
    run_streamlit_score_job,
    run_streamlit_train_job,
)


CFG_PATH = Path("configs/ml_pipeline_v1.yaml")


def _prep_canonical(root: Path, data_version: str) -> None:
    canonical_dir = root / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def _prepare_root(root: Path, *, data_version: str, qc_run: str) -> None:
    _prep_canonical(root, data_version)
    qc = run_qc(data_version=data_version, artifacts_root=root, qc_run=qc_run)
    assert qc["qc_status"] in {"OK", "WARN"}


def test_t15_07_train_and_score_job_builders_support_fixed_run_ids_and_config() -> None:
    artifacts = Path("/tmp/artifacts")
    cfg = Path("configs/ml_pipeline_v1.yaml")

    train_req = build_train_job_request(
        data_version="dv_demo",
        qc_run="qc_demo",
        artifacts_root=artifacts,
        model_version="model_fixed",
        config_path=cfg,
    )
    assert train_req.argv == [
        "train",
        "--data-version",
        "dv_demo",
        "--qc-run",
        "qc_demo",
        "--artifacts",
        str(artifacts),
        "--model-version",
        "model_fixed",
        "--config",
        str(cfg),
    ]

    score_req = build_score_job_request(
        data_version="dv_demo",
        model_version="model_fixed",
        artifacts_root=artifacts,
        scoring_run="score_fixed",
        config_path=cfg,
    )
    assert score_req.argv == [
        "score",
        "--data-version",
        "dv_demo",
        "--model-version",
        "model_fixed",
        "--artifacts",
        str(artifacts),
        "--scoring-run",
        "score_fixed",
        "--config",
        str(cfg),
    ]

    assert build_streamlit_train_job_request(
        data_version="dv_demo",
        qc_run="qc_demo",
        artifacts_root=artifacts,
        model_version="model_fixed",
        config_path=cfg,
    ).argv == train_req.argv
    assert build_streamlit_score_job_request(
        data_version="dv_demo",
        model_version="model_fixed",
        artifacts_root=artifacts,
        scoring_run="score_fixed",
        config_path=cfg,
    ).argv == score_req.argv


def test_t15_07_cli_vs_jobrunner_vs_streamlit_train_and_score_surfaces_match(tmp_path: Path) -> None:
    dv = "dv_t15_07_ifaces"
    qc_run = "qc_t15_07_ifaces"
    model_version = "model_t15_07_ifaces"
    scoring_run = "score_t15_07_ifaces"

    cli_root = tmp_path / "cli_artifacts"
    web_root = tmp_path / "web_artifacts"
    streamlit_root = tmp_path / "streamlit_artifacts"

    for root in (cli_root, web_root, streamlit_root):
        _prepare_root(root, data_version=dv, qc_run=qc_run)

    cli_rc = cli_main([
        "train",
        "--data-version",
        dv,
        "--qc-run",
        qc_run,
        "--artifacts",
        str(cli_root),
        "--model-version",
        model_version,
        "--config",
        str(CFG_PATH),
    ])
    assert cli_rc == 0

    web_rc = run_pipeline_job(
        build_train_job_request(
            data_version=dv,
            qc_run=qc_run,
            artifacts_root=web_root,
            model_version=model_version,
            config_path=CFG_PATH,
        )
    )
    assert web_rc == 0

    streamlit_train = run_streamlit_train_job(
        data_version=dv,
        qc_run=qc_run,
        artifacts_root=streamlit_root,
        model_version=model_version,
        config_path=CFG_PATH,
    )
    assert streamlit_train.exit_code == 0

    cli_model = build_model_surface_snapshot(artifacts_root=cli_root, data_version=dv, model_version=model_version)
    web_model = build_model_surface_snapshot(artifacts_root=web_root, data_version=dv, model_version=model_version)
    streamlit_model = build_model_surface_snapshot(artifacts_root=streamlit_root, data_version=dv, model_version=model_version)

    assert web_model == cli_model
    assert streamlit_model == cli_model
    assert load_model_registry(artifacts_root=cli_root, data_version=dv)["latest"] == model_version
    assert load_model_registry(artifacts_root=web_root, data_version=dv)["latest"] == model_version
    assert load_model_registry(artifacts_root=streamlit_root, data_version=dv)["latest"] == model_version

    cli_score_rc = cli_main([
        "score",
        "--data-version",
        dv,
        "--model-version",
        model_version,
        "--artifacts",
        str(cli_root),
        "--scoring-run",
        scoring_run,
        "--config",
        str(CFG_PATH),
    ])
    assert cli_score_rc == 0

    web_score_rc = run_pipeline_job(
        build_score_job_request(
            data_version=dv,
            model_version=model_version,
            artifacts_root=web_root,
            scoring_run=scoring_run,
            config_path=CFG_PATH,
        )
    )
    assert web_score_rc == 0

    streamlit_score = run_streamlit_score_job(
        data_version=dv,
        model_version=model_version,
        artifacts_root=streamlit_root,
        scoring_run=scoring_run,
        config_path=CFG_PATH,
    )
    assert streamlit_score.exit_code == 0

    cli_scoring = build_scoring_surface_snapshot(artifacts_root=cli_root, data_version=dv, scoring_run=scoring_run)
    web_scoring = build_scoring_surface_snapshot(artifacts_root=web_root, data_version=dv, scoring_run=scoring_run)
    streamlit_scoring = build_scoring_surface_snapshot(artifacts_root=streamlit_root, data_version=dv, scoring_run=scoring_run)

    assert web_scoring == cli_scoring
    assert streamlit_scoring == cli_scoring
    assert load_scoring_registry(artifacts_root=cli_root, data_version=dv)["latest"] == scoring_run
    assert load_scoring_registry(artifacts_root=web_root, data_version=dv)["latest"] == scoring_run
    assert load_scoring_registry(artifacts_root=streamlit_root, data_version=dv)["latest"] == scoring_run
