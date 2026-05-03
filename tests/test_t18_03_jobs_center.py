from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.jobs_center import (
    cancel_job_action,
    get_job_view,
    list_job_family_view,
    list_jobs_view,
    read_job_artifact_preview,
    read_job_log_tail,
    retry_job_action,
)
from web_cabinet.auth import hash_password
from web_cabinet import rbac
from core.infra.web_db import create_job, mark_job_finished, mark_job_running


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")


def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st_test_jobs_center",
    }


def test_t18_03_jobs_center_lists_refs_logs_and_artifacts(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    artifacts_root = Path(ctx.artifacts_dir)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    log_path = tmp_path / "logs" / "score.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("job started\nscore done\n", encoding="utf-8")
    artifact_path = artifacts_root / "dv_demo" / "reports_regular" / "rep_demo" / "exports" / "report.txt"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("regular report preview\n", encoding="utf-8")

    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        job_id = create_job(
            conn,
            tenant_id="default",
            user_id=1,
            user="operator",
            kind="score",
            command="python -m genomeai.cli score",
            args={"data_version": "dv_demo", "model_version": "mdl_demo", "scoring_run": "score_demo"},
            log_path=log_path,
        )
        assert mark_job_running(conn, job_id) is True
        mark_job_finished(
            conn,
            job_id,
            status="done",
            exit_code=0,
            result={"kv": {"data_version": "dv_demo", "model_version": "mdl_demo", "scoring_run": "score_demo", "report_version": "rep_demo", "run_id": "score_demo"}},
            artifacts=[str(artifact_path)],
        )
    finally:
        conn.close()

    jobs = list_jobs_view(ctx, status="done", pipeline="score", limit=20)
    assert len(jobs) == 1
    row = jobs[0]
    assert row["data_version"] == "dv_demo"
    assert row["model_version"] == "mdl_demo"
    assert row["scoring_run"] == "score_demo"
    assert row["report_version"] == "rep_demo"
    assert row["artifacts_count"] >= 1

    detail = get_job_view(ctx, job_id=job_id)
    assert detail is not None
    assert detail["run_refs"]["job_id"] == job_id
    assert detail["run_refs"]["data_version"] == "dv_demo"

    log_payload = read_job_log_tail(ctx, job_id=job_id, tail_bytes=4096)
    assert "score done" in log_payload["text"]

    artifact = detail["artifacts"][0]
    preview = read_job_artifact_preview(ctx, job_id=job_id, virtual_path=artifact["virtual_path"], max_bytes=4096)
    assert "regular report preview" in preview["text"]


def test_t18_03_jobs_center_retry_and_cancel_use_backend_adapters(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        failed_job_id = create_job(
            conn,
            tenant_id="default",
            user_id=1,
            user="admin",
            kind="report",
            command="python -m genomeai.cli report",
            args={"data_version": "dv_retry", "scoring_run": "score_retry", "report_version": "rep_retry"},
            log_path=log_dir / "report.log",
        )
        assert mark_job_running(conn, failed_job_id) is True
        mark_job_finished(
            conn,
            failed_job_id,
            status="failed",
            exit_code=1,
            result={"kv": {"data_version": "dv_retry", "scoring_run": "score_retry", "report_version": "rep_retry", "run_id": "rep_retry"}},
            artifacts=[],
            error_text="report generation failed",
        )

        queued_job_id = create_job(
            conn,
            tenant_id="default",
            user_id=1,
            user="admin",
            kind="qc",
            command="python -m genomeai.cli qc",
            args={"data_version": "dv_cancel", "qc_run": "qc_cancel"},
            log_path=log_dir / "qc.log",
        )
    finally:
        conn.close()

    retry_res = retry_job_action(ctx, job_id=failed_job_id, user=_user(rbac.ROLE_ADMIN))
    assert retry_res.ok is True
    assert retry_res.job is not None
    assert retry_res.job["retry_of_job_id"] == failed_job_id
    assert retry_res.job["status"] == "queued"

    cancel_res = cancel_job_action(ctx, job_id=queued_job_id, user=_user(rbac.ROLE_OPERATOR))
    assert cancel_res.ok is True
    assert cancel_res.job is not None
    assert cancel_res.job["status"] == "cancelled"

    family = list_job_family_view(ctx, job_id=retry_res.job["id"])
    family_ids = {int(row["id"]) for row in family}
    assert failed_job_id in family_ids
    assert int(retry_res.job["id"]) in family_ids


def test_t18_03_jobs_center_is_visible_for_operator_and_hidden_for_viewer() -> None:
    from pathlib import Path
    from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config

    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    operator_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_OPERATOR,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, [])),
    )
    assert "jobs_center" in flatten_shell_sections(operator_sections)

    viewer_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_VIEWER,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_VIEWER, [])),
    )
    assert "jobs_center" not in flatten_shell_sections(viewer_sections)
