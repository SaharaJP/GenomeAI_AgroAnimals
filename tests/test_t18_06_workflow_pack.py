from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from genomeai.qc import run_qc
from genomeai.report import run_report
from genomeai.score import run_scoring
from genomeai.train import train_productivity_model
from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config
from streamlit_app.workflow_pack import (
    create_streamlit_decision,
    get_report_approval_view,
    launch_pack_job,
    list_decisions_view,
    list_pack_entries,
    list_tasks_view,
    report_approval_action,
)
from web_cabinet import rbac
from web_cabinet.auth import hash_password
from core.workflow import AlertCreate, DecisionCreate, TaskCreate, append_decision, create_alert, create_task


ROOT = Path(__file__).resolve().parents[1]


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")


def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st_test_t18_06",
    }


def _prep_pipeline(ctx, *, dv: str = "dv_t18_06") -> dict[str, str]:
    canonical_dir = Path(ctx.artifacts_dir) / dv / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base = ROOT / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())

    qc = run_qc(data_version=dv, artifacts_root=Path(ctx.artifacts_dir))
    tr = train_productivity_model(artifacts_root=Path(ctx.artifacts_dir), data_version=dv, qc_run=qc["qc_run"])
    sc = run_scoring(artifacts_root=Path(ctx.artifacts_dir), data_version=dv, model_version=tr["model_version"])
    rep = run_report(
        artifacts_root=Path(ctx.artifacts_dir),
        data_version=dv,
        qc_run=qc["qc_run"],
        model_version=tr["model_version"],
        scoring_run=sc["scoring_run"],
        mode="fallback",
        make_pdf=False,
    )
    return {
        "data_version": dv,
        "qc_run": qc["qc_run"],
        "model_version": tr["model_version"],
        "scoring_run": sc["scoring_run"],
        "report_version": rep["report_version"],
    }


def test_t18_06_shell_visibility_new_pages_and_legacy_hidden() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    operator_flat = flatten_shell_sections(build_shell_for_user(cfg=cfg, role=rbac.ROLE_OPERATOR, permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, []))))
    assert "decisions_ops" in operator_flat
    assert "tasks_workflow_ops" in operator_flat
    assert "pilot_pack_ops" in operator_flat
    assert "decision_log" not in operator_flat
    assert "worklist" not in operator_flat

    viewer_flat = flatten_shell_sections(build_shell_for_user(cfg=cfg, role=rbac.ROLE_VIEWER, permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_VIEWER, []))))
    assert "decisions_ops" not in viewer_flat
    assert "tasks_workflow_ops" not in viewer_flat
    assert "pilot_pack_ops" not in viewer_flat


def test_t18_06_report_approval_and_manual_decision_are_recorded(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    versions = _prep_pipeline(ctx)
    user = _user(rbac.ROLE_ADMIN)
    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    conn.close()

    approve = report_approval_action(
        ctx,
        user=user,
        data_version=versions["data_version"],
        report_version=versions["report_version"],
        action="approve",
        comment="approved from streamlit",
    )
    assert approve.ok is True
    approval = get_report_approval_view(ctx, tenant_id="default", data_version=versions["data_version"], report_version=versions["report_version"])
    assert approval["status"] == "approved"

    manual = create_streamlit_decision(
        ctx,
        user=user,
        recommendation_id=None,
        action="pack.review",
        reason="ready",
        comment="pilot pack can be prepared",
        related_alert=None,
        object_type="report",
        object_id=versions["report_version"],
        farm_id=None,
        group_id=None,
        data_version=versions["data_version"],
        model_version=versions["model_version"],
        report_version=versions["report_version"],
        qc_run=versions["qc_run"],
        scoring_run=versions["scoring_run"],
        metadata={"source": "test"},
    )
    assert manual.ok is True

    decisions = list_decisions_view(ctx, tenant_id="default", data_version=versions["data_version"], report_version=versions["report_version"], limit=50)
    actions = {str(row.get("action") or "") for row in decisions}
    assert "report.approve" in actions
    assert "pack.review" in actions

    conn = sqlite3.connect(str(Path(ctx.web_storage_dir) / "web.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("select action from audit_log where action in ('reports.approve.streamlit','decision_log.append.streamlit')").fetchall()
    finally:
        conn.close()
    assert {str(r[0]) for r in rows} >= {"reports.approve.streamlit", "decision_log.append.streamlit"}


def test_t18_06_linkage_and_pack_job(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    versions = _prep_pipeline(ctx)
    user = _user(rbac.ROLE_OPERATOR)

    os.environ["GENOMEAI_PROJECT_ROOT"] = str(ROOT)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(Path(ctx.artifacts_dir))
    os.environ["GENOMEAI_WEB_STORAGE"] = str(Path(ctx.web_storage_dir))
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"

    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        alert_id = create_alert(
            conn,
            tenant_id="default",
            a=AlertCreate(
                alert_type="score.low_confidence",
                title="Check scoring result",
                source="score",
                cause="manual test",
                confidence=0.75,
                object_type="report",
                object_id=versions["report_version"],
                deadline=None,
                owner_user_id=1,
                attachments=[],
                why={"report_version": versions["report_version"]},
                what_to_do=[{"step": 1, "text": "Review report"}],
                data_version=versions["data_version"],
                qc_run=versions["qc_run"],
                model_version=versions["model_version"],
                scoring_run=versions["scoring_run"],
                report_version=versions["report_version"],
                dedupe_key="test:t18_06:alert",
            ),
        )
        task_id = create_task(
            conn,
            tenant_id="default",
            t=TaskCreate(
                task_type="report_followup",
                title="Follow up report",
                priority=3,
                related_alert=str(alert_id),
                object_type="report",
                object_id=versions["report_version"],
                attachments=[],
                why={"report_version": versions["report_version"]},
                what_to_do=[{"step": 1, "text": "Prepare pilot pack"}],
                data_version=versions["data_version"],
                qc_run=versions["qc_run"],
                model_version=versions["model_version"],
                scoring_run=versions["scoring_run"],
                report_version=versions["report_version"],
                dedupe_key="test:t18_06:task",
            ),
        )
        append_decision(
            conn,
            tenant_id="default",
            d=DecisionCreate(
                recommendation_id=None,
                action="report.reviewed",
                user_id=1,
                username="operator",
                reason="linked",
                comment="linked entities ready",
                related_alert=str(alert_id),
                object_type="report",
                object_id=versions["report_version"],
                farm_id=None,
                group_id=None,
                data_version=versions["data_version"],
                model_version=versions["model_version"],
                report_version=versions["report_version"],
                qc_run=versions["qc_run"],
                scoring_run=versions["scoring_run"],
                metadata={"task_id": task_id},
            ),
        )
    finally:
        conn.close()

    tasks = list_tasks_view(ctx, tenant_id="default", data_version=versions["data_version"], related_alert=str(alert_id), limit=20)
    assert any(str(t.get("task_id")) == str(task_id) for t in tasks)
    decisions = list_decisions_view(ctx, tenant_id="default", data_version=versions["data_version"], related_alert=str(alert_id), limit=20)
    assert any(str(d.get("report_version")) == versions["report_version"] for d in decisions)

    pack = launch_pack_job(
        ctx,
        user=user,
        data_version=versions["data_version"],
        qc_run=versions["qc_run"],
        model_version=versions["model_version"],
        scoring_run=versions["scoring_run"],
        report_version=versions["report_version"],
    )
    assert pack.ok is True
    assert pack.job_id is not None

    worker_module = importlib.import_module("web_cabinet.worker")
    worker_module = importlib.reload(worker_module)
    worker = worker_module.JobWorker()
    worker.run_until_empty(max_jobs=50)

    packs = list_pack_entries(ctx, data_version=versions["data_version"])
    assert packs
    latest = packs[0]
    assert latest["report_version"] == versions["report_version"]
    assert latest["pack_zip_virtual_path"]
