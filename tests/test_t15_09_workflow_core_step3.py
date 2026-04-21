from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from core.workflow import (
    AlertCreate,
    TaskCreate,
    acknowledge_alert_use_case,
    alert_resolve_reason_codes,
    close_task_use_case,
    create_alert,
    create_task,
    get_alert,
    get_task,
    resolve_alert_use_case,
    take_task_use_case,
    task_close_reason_codes,
    task_close_status_options,
    update_task_use_case,
)
from web_cabinet.db import init_db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t15_09_workflow_policy_exports_expose_reason_codes() -> None:
    assert set(task_close_status_options()) == {"done", "cancelled"}
    assert "COMPLETED" in set(task_close_reason_codes(status="done"))
    assert "NOT_FEASIBLE" in set(task_close_reason_codes(status="cancelled"))
    assert "INVESTIGATED" in set(alert_resolve_reason_codes())


def test_t15_09_workflow_lifecycle_use_cases_preserve_status_and_linkage() -> None:
    conn = _conn()
    try:
        alert_id = create_alert(
            conn,
            tenant_id="default",
            a=AlertCreate(
                alert_type="health_risk",
                title="High health risk",
                source="ML",
                cause="model_flag",
                confidence=0.83,
                object_type="animal",
                object_id="A-100",
                deadline=None,
                owner_user_id=2,
                attachments=[],
                why={"severity": "HIGH"},
                what_to_do=[{"step": "inspect"}],
                data_version="dv_step3",
                scoring_run="score_step3",
                dedupe_key="alert:a-100:health",
            ),
        )
        ack = acknowledge_alert_use_case(conn=conn, tenant_id="default", alert_id=alert_id, user_id=2)
        assert ack["status"] == "acknowledged"
        assert (ack["after"] or {}).get("alert_id") == alert_id

        resolved = resolve_alert_use_case(
            conn=conn,
            tenant_id="default",
            alert_id=alert_id,
            user_id=2,
            reason="INVESTIGATED",
        )
        assert resolved["status"] == "resolved"
        assert resolved["reason"] == "INVESTIGATED"
        assert get_alert(conn, tenant_id="default", alert_id=alert_id)["status"] == "resolved"

        linked_alert_id = create_alert(
            conn,
            tenant_id="default",
            a=AlertCreate(
                alert_type="QC.PK_DUPLICATE",
                title="Duplicate animal_id",
                source="qc2",
                cause="pk_animals",
                confidence=1.0,
                object_type="animal",
                object_id="A-101",
                deadline=None,
                owner_user_id=None,
                attachments=[],
                why={"severity": "MAJOR"},
                what_to_do=[{"step": "fix source"}],
                data_version="dv_step3",
                qc_run="qc_step3",
                dedupe_key="alert:a-101:qc",
            ),
        )
        task_id = create_task(
            conn,
            tenant_id="default",
            t=TaskCreate(
                task_type="qc_followup",
                title="QC follow-up",
                domain="qc",
                priority=2,
                due_at=None,
                owner_user_id=None,
                related_alert=linked_alert_id,
                object_type="animal",
                object_id="A-101",
                data_version="dv_step3",
                qc_run="qc_step3",
                dedupe_key="task:a-101:qc",
            ),
        )
        taken = take_task_use_case(conn=conn, tenant_id="default", task_id=task_id, user_id=2)
        assert (taken["after"] or {}).get("status") == "in_progress"

        updated = update_task_use_case(
            conn=conn,
            tenant_id="default",
            task_id=task_id,
            patch={"priority": 1, "due_at": "2099-01-02T00:00:00+00:00"},
        )
        assert int((updated["after"] or {}).get("priority") or 0) == 1
        assert (updated["after"] or {}).get("sla_source") in {"derived.from_due_at", "user.due_at", "cfg.default"}

        closed = close_task_use_case(
            conn=conn,
            tenant_id="default",
            task_id=task_id,
            user_id=2,
            username="zootech",
            status="done",
            reason="COMPLETED",
            comment="ok",
            resolve_related_alert=True,
        )
        assert closed["status"] == "done"
        assert closed["reason"] == "COMPLETED"
        assert "COMPLETED" in set(closed["reason_codes"])
        assert get_task(conn, tenant_id="default", task_id=task_id)["status"] == "done"
        assert get_alert(conn, tenant_id="default", alert_id=linked_alert_id)["status"] == "resolved"
    finally:
        conn.close()


def test_t15_09_first_party_adapters_use_core_workflow_lifecycle_use_cases() -> None:
    import web_cabinet.app as appmod

    app_src = inspect.getsource(appmod)
    assert "acknowledge_alert_use_case" in app_src
    assert "resolve_alert_use_case" in app_src
    assert "take_task_use_case" in app_src
    assert "update_task_use_case" in app_src
    assert "close_task_use_case" in app_src

    for rel in [
        "streamlit_app/pages/5_Alert_Center_v2.py",
        "streamlit_app/pages/7_Worklist_v1.py",
    ]:
        src = Path(rel).read_text(encoding="utf-8")
        assert "_use_case" in src, rel
        assert "core.workflow" in src, rel
