from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.infra.web_db import create_job, mark_job_finished, mark_job_running
from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.jobs_center import (
    get_job_view,
    list_job_family_view,
    list_jobs_view,
    read_job_artifact_preview,
    read_job_log_bytes,
    retry_job_action,
)
from streamlit_app.jobs_workspace import (
    build_job_detail_bundle,
    build_jobs_overview,
    filter_jobs,
    sanitize_log_text,
    source_page_for_job,
)
from web_cabinet import rbac
from web_cabinet.auth import hash_password


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")



def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st_test_t19_06",
    }



def test_t19_06_jobs_workspace_builds_overview_and_source_links(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    artifacts_root = Path(ctx.artifacts_dir)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "report.log").write_text("report started\nreport done\n", encoding="utf-8")
    (log_dir / "score.log").write_text("score started\nscore failed\n", encoding="utf-8")
    artifact_path = artifacts_root / "dv_t19_06" / "reports_regular" / "rep_t19_06" / "exports" / "report.txt"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("report preview\n", encoding="utf-8")

    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        report_job_id = create_job(
            conn,
            tenant_id="default",
            user_id=1,
            user="operator",
            kind="report",
            command="python -m genomeai.cli report",
            args={"data_version": "dv_t19_06", "scoring_run": "score_t19_06", "report_version": "rep_t19_06"},
            log_path=log_dir / "report.log",
        )
        assert mark_job_running(conn, report_job_id) is True
        mark_job_finished(
            conn,
            report_job_id,
            status="done",
            exit_code=0,
            result={"kv": {"data_version": "dv_t19_06", "scoring_run": "score_t19_06", "report_version": "rep_t19_06", "run_id": "rep_t19_06"}},
            artifacts=[str(artifact_path)],
        )

        failed_score_job_id = create_job(
            conn,
            tenant_id="default",
            user_id=1,
            user="operator",
            kind="score",
            command="python -m genomeai.cli score",
            args={"data_version": "dv_t19_06", "model_version": "mdl_t19_06", "scoring_run": "score_failed"},
            log_path=log_dir / "score.log",
        )
        assert mark_job_running(conn, failed_score_job_id) is True
        mark_job_finished(
            conn,
            failed_score_job_id,
            status="failed",
            exit_code=1,
            result={"kv": {"data_version": "dv_t19_06", "model_version": "mdl_t19_06", "scoring_run": "score_failed", "run_id": "score_failed"}},
            artifacts=[],
            error_text="score failed on malformed input",
        )
    finally:
        conn.close()

    rows = list_jobs_view(ctx, limit=20)
    filtered = filter_jobs(rows, pipelines=["report"], statuses=["done"])
    overview = build_jobs_overview(filtered)
    assert overview["metrics"][0]["value"] == 1
    assert overview["table_rows"][0]["source_page"] == "📝 Report Operations"

    job = get_job_view(ctx, job_id=report_job_id)
    assert job is not None
    detail = build_job_detail_bundle(job, family=list_job_family_view(ctx, job_id=report_job_id))
    assert detail["source_page"]["page"] == "pages/30_Report_Operations.py"
    assert any(card["label"] == "report_version" and card["value"] == "rep_t19_06" for card in detail["version_cards"])

    preview = read_job_artifact_preview(ctx, job_id=report_job_id, virtual_path=job["artifacts"][0]["virtual_path"], max_bytes=2048)
    assert "report preview" in preview["text"]

    log_bytes = read_job_log_bytes(ctx, job_id=report_job_id)
    assert log_bytes["file_name"] == "report.log"

    failed_source = source_page_for_job(get_job_view(ctx, job_id=failed_score_job_id) or {})
    assert failed_source["page"] == "pages/29_Score_Operations.py"



def test_t19_06_jobs_workspace_sanitizes_traceback_for_user_mode() -> None:
    raw = """job started
Traceback (most recent call last):
  File \"worker.py\", line 1, in <module>
    raise RuntimeError('boom')
RuntimeError: boom
job finished
"""
    cleaned = sanitize_log_text(raw, include_traceback=False)
    assert cleaned["hidden_traceback"] is True
    assert "Traceback" not in cleaned["text"]
    assert "worker.py" not in cleaned["text"]
    assert "job started" in cleaned["text"]
    assert "job finished" in cleaned["text"]

    raw_mode = sanitize_log_text(raw, include_traceback=True)
    assert "Traceback" in raw_mode["text"]



def test_t19_06_jobs_workspace_retry_lineage_is_visible(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "train.log").write_text("train failed\n", encoding="utf-8")

    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        failed_job_id = create_job(
            conn,
            tenant_id="default",
            user_id=1,
            user="admin",
            kind="train",
            command="python -m genomeai.cli train",
            args={"data_version": "dv_retry", "qc_run": "qc_retry", "model_version": "mdl_retry"},
            log_path=log_dir / "train.log",
        )
        assert mark_job_running(conn, failed_job_id) is True
        mark_job_finished(
            conn,
            failed_job_id,
            status="failed",
            exit_code=1,
            result={"kv": {"data_version": "dv_retry", "qc_run": "qc_retry", "model_version": "mdl_retry", "run_id": "mdl_retry"}},
            artifacts=[],
            error_text="train failed",
        )
    finally:
        conn.close()

    retry_res = retry_job_action(ctx, job_id=failed_job_id, user=_user(rbac.ROLE_ADMIN))
    assert retry_res.ok is True and retry_res.job is not None
    family = list_job_family_view(ctx, job_id=int(retry_res.job["id"]))
    detail = build_job_detail_bundle(retry_res.job, family=family)
    family_ids = {int(row["job_id"]) for row in detail["family_rows"]}
    assert failed_job_id in family_ids
    assert int(retry_res.job["id"]) in family_ids
