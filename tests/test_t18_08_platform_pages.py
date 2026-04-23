from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from genomeai.qc import run_qc
from genomeai.report import run_report
from genomeai.score import run_scoring
from genomeai.train import train_productivity_model
from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.platform_pages import (
    connector_run_now,
    contract_catalog_view,
    create_weekly_plan_action,
    export_feedback_admin_dataset,
    feedback_admin_view,
    list_connectors_view,
    list_pending_weekly_plans_view,
    list_report_approvals_view,
    weekly_plan_action,
)
from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config
from streamlit_app.workflow_pack import report_approval_action
from web_cabinet import rbac
from web_cabinet.auth import hash_password
from web_cabinet.feedback_v1 import FeedbackCreate, record_feedback

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
        "request_id": "st_test_t18_08",
    }


def _prep_pipeline(ctx, *, dv: str = "dv_t18_08") -> dict[str, str]:
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


def test_t18_08_shell_visibility_platform_pages() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    admin_flat = flatten_shell_sections(build_shell_for_user(cfg=cfg, role=rbac.ROLE_ADMIN, permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_ADMIN, []))))
    for key in ("connectors_platform", "contracts_data_catalog", "approvals_center", "weekly_plans_platform", "feedback_admin_surface"):
        assert key in admin_flat

    viewer_flat = flatten_shell_sections(build_shell_for_user(cfg=cfg, role=rbac.ROLE_VIEWER, permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_VIEWER, []))))
    assert "contracts_data_catalog" in viewer_flat
    for key in ("connectors_platform", "approvals_center", "weekly_plans_platform", "feedback_admin_surface"):
        assert key not in viewer_flat


def test_t18_08_connectors_and_contract_catalog(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    connect_web_db(ctx, hash_password_fn=hash_password).close()

    view = list_connectors_view(ctx, tenant_id="default")
    connector_ids = {str(row.get("connector_id") or "") for row in view.get("catalog") or []}
    assert {"demo_file_pull", "demo_api_stub", "demo_onec_stub"}.issubset(connector_ids)

    run_res = connector_run_now(ctx, user=_user(rbac.ROLE_OPERATOR), connector_id="demo_file_pull", force=True)
    assert run_res.ok is True
    assert run_res.job_id is not None

    catalog = contract_catalog_view(ctx)
    datasets = {str(row.get("dataset") or "") for row in catalog.get("rows") or []}
    assert {"dm_farms", "dm_animals", "dm_lactations"}.issubset(datasets)

    conn = sqlite3.connect(str(Path(ctx.web_storage_dir) / "web.db"))
    conn.row_factory = sqlite3.Row
    try:
        actions = [str(r[0]) for r in conn.execute("select action from audit_log where action='connector.run_now.streamlit'").fetchall()]
    finally:
        conn.close()
    assert "connector.run_now.streamlit" in actions


def test_t18_08_approvals_weekly_plans_and_feedback_export(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    versions = _prep_pipeline(ctx)
    connect_web_db(ctx, hash_password_fn=hash_password).close()

    rep = report_approval_action(ctx, user=_user(rbac.ROLE_DIRECTOR), data_version=versions["data_version"], report_version=versions["report_version"], action="approve", comment="ok")
    assert rep.ok is True
    approvals = list_report_approvals_view(ctx, tenant_id="default")
    assert any(str(row.get("report_version") or "") == versions["report_version"] and str(row.get("status") or "") == "approved" for row in approvals)

    plan = create_weekly_plan_action(
        ctx,
        user=_user(rbac.ROLE_ZOOTECH),
        name="Weekly plan",
        week_start="2026-03-30",
        summary="test plan",
        farm_id="farm_demo",
        data_version=versions["data_version"],
        action_items=[{"key": "review-report", "title": "Review report", "what_to_do": [{"step": 1, "text": "check report"}]}],
    )
    assert plan.ok is True
    plan_id = str((plan.payload or {}).get("plan_id") or "")
    req = weekly_plan_action(ctx, user=_user(rbac.ROLE_ZOOTECH), plan_id=plan_id, action="request_approval", comment="please approve")
    assert req.ok is True
    pending = list_pending_weekly_plans_view(ctx, tenant_id="default")
    assert any(str(row.get("plan_id") or "") == plan_id for row in pending.get("weekly_plans") or [])
    appr = weekly_plan_action(ctx, user=_user(rbac.ROLE_DIRECTOR), plan_id=plan_id, action="approve", comment="approved")
    assert appr.ok is True
    exp = weekly_plan_action(ctx, user=_user(rbac.ROLE_DIRECTOR), plan_id=plan_id, action="export_pdf")
    assert exp.ok is True
    assert str((exp.payload or {}).get("pdf_rel_path") or "")

    conn = connect_web_db(ctx)
    try:
        record_feedback(
            conn,
            tenant_id="default",
            user_id=1,
            username="director",
            fc=FeedbackCreate(
                recommendation_id=None,
                decision="accepted",
                reason_code="CONFIRMED_BY_SPECIALIST",
                comment="good",
                related_alert=None,
                task_id=None,
                object_type="report",
                object_id=versions["report_version"],
                farm_id="farm_demo",
                group_id=None,
                data_version=versions["data_version"],
                model_version=versions["model_version"],
                report_version=versions["report_version"],
                qc_run=versions["qc_run"],
                scoring_run=versions["scoring_run"],
                recommendation_created_at=None,
                feedback_source="platform_test",
                metadata={"source": "test"},
            ),
        )
    finally:
        conn.close()

    fb = feedback_admin_view(ctx, tenant_id="default", data_version=versions["data_version"], report_version=versions["report_version"], scoring_run=versions["scoring_run"], feedback_source="platform_test")
    metrics = (fb.get("metrics") or {}).get("metrics") or {}
    assert int(metrics.get("feedback_total") or 0) >= 1

    export = export_feedback_admin_dataset(ctx, user=_user(rbac.ROLE_ADMIN), data_version=versions["data_version"], scoring_run=versions["scoring_run"], report_version=versions["report_version"], feedback_source="platform_test")
    assert export.ok is True
    assert str((((export.payload or {}).get("outputs") or {}).get("feedback_dataset_csv") or ""))
