from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from streamlit_app.pipeline_jobs import build_streamlit_report_job_request
from streamlit_app.pipeline_ops import (
    get_pipeline_state,
    launch_qc_job,
    launch_report_job,
    launch_score_job,
    launch_train_job,
    list_report_entries,
)
from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config
from streamlit_app.upload_ingest import build_identity_mapping_bytes, launch_ingest_jobs, save_named_upload_bytes
from web_cabinet import rbac


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")


def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st-test-pipeline-ops",
    }


def test_t18_05_shell_exposes_pipeline_ops_for_operator_not_viewer() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    operator_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_OPERATOR,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, [])),
    )
    viewer_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_VIEWER,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_VIEWER, [])),
    )
    flat_operator = flatten_shell_sections(operator_sections)
    flat_viewer = flatten_shell_sections(viewer_sections)
    for key in ("qc_ops", "train_ops", "score_ops", "report_ops"):
        assert key in flat_operator
        assert key not in flat_viewer


def test_t18_05_report_request_supports_llm_model() -> None:
    req = build_streamlit_report_job_request(
        data_version="dv_demo",
        qc_run="qc_demo",
        model_version="model_demo",
        scoring_run="score_demo",
        mode="llm",
        artifacts_root=Path("artifacts"),
        llm_model="gpt-5-mini",
    )
    assert req.kind == "report"
    assert "--mode" in req.argv
    assert "llm" in req.argv
    assert "--llm-model" in req.argv
    assert "gpt-5-mini" in req.argv


def test_t18_05_viewer_cannot_launch_pipeline_ops(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert launch_qc_job(ctx, user=_user(rbac.ROLE_VIEWER), data_version="dv_x").ok is False
    assert launch_train_job(ctx, user=_user(rbac.ROLE_VIEWER), data_version="dv_x", qc_run="qc_x").ok is False
    assert launch_score_job(ctx, user=_user(rbac.ROLE_VIEWER), data_version="dv_x", model_version="m_x").ok is False
    assert launch_report_job(ctx, user=_user(rbac.ROLE_VIEWER), data_version="dv_x", qc_run="qc_x", model_version="m_x", scoring_run="s_x").ok is False


def test_t18_05_end_to_end_pipeline_ops_smoke(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ctx = _ctx(tmp_path)
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(ctx.artifacts_dir))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(ctx.web_storage_dir))
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")

    base = repo_root / "data" / "examples"
    datasets = []
    for dataset_key, file_name in (("farms", "dm_farms.csv"), ("animals", "dm_animals.csv"), ("lactations", "dm_lactations.csv")):
        saved = save_named_upload_bytes(ctx, filename=file_name, content=(base / file_name).read_bytes())
        mapping_saved = save_named_upload_bytes(
            ctx,
            filename=f"{dataset_key}_identity.yaml",
            content=build_identity_mapping_bytes(dataset_key=dataset_key, file_path=saved),
            is_mapping=True,
        )
        datasets.append({"dataset_key": dataset_key, "file_path": str(saved), "mapping_path": str(mapping_saved)})

    dv = "dv_t18_05_smoke"
    ingest = launch_ingest_jobs(ctx, user=_user(rbac.ROLE_OPERATOR), data_version=dv, datasets=datasets)
    assert len(ingest.created_jobs) == 3

    worker_module = importlib.import_module("web_cabinet.worker")
    worker_module = importlib.reload(worker_module)
    worker = worker_module.JobWorker()
    worker.run_until_empty(max_jobs=50)

    qc = launch_qc_job(ctx, user=_user(rbac.ROLE_OPERATOR), data_version=dv)
    assert qc.ok and qc.job_id
    worker.run_until_empty(max_jobs=50)

    state_after_qc = get_pipeline_state(ctx, data_version=dv)
    qc_runs = list(state_after_qc.get("qc_runs") or [])
    assert qc_runs
    qc_run = qc_runs[-1]

    train = launch_train_job(ctx, user=_user(rbac.ROLE_OPERATOR), data_version=dv, qc_run=qc_run)
    assert train.ok and train.job_id
    worker.run_until_empty(max_jobs=50)

    state_after_train = get_pipeline_state(ctx, data_version=dv)
    model_versions = list(state_after_train.get("model_versions") or [])
    assert model_versions
    model_version = model_versions[-1]

    score = launch_score_job(ctx, user=_user(rbac.ROLE_OPERATOR), data_version=dv, model_version=model_version)
    assert score.ok and score.job_id
    worker.run_until_empty(max_jobs=50)

    state_after_score = get_pipeline_state(ctx, data_version=dv)
    scoring_runs = list(state_after_score.get("scoring_runs") or [])
    assert scoring_runs
    scoring_run = scoring_runs[-1]

    report = launch_report_job(
        ctx,
        user=_user(rbac.ROLE_OPERATOR),
        data_version=dv,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode="fallback",
    )
    assert report.ok and report.job_id
    worker.run_until_empty(max_jobs=50)

    state_after_report = get_pipeline_state(ctx, data_version=dv)
    report_versions = list(state_after_report.get("report_versions") or [])
    assert report_versions
    entries = list_report_entries(ctx, data_version=dv)
    assert entries
    latest = entries[-1]
    assert latest["report_version"] in report_versions
    assert latest["mode_requested"] == "fallback"
    assert latest["summary"]
    assert latest["fact_pack_virtual_path"]
