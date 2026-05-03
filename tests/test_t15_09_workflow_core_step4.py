from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from core.workflow import (
    AlertCreate,
    TaskCreate,
    alert_status_options,
    create_alert,
    create_task,
    operational_summary_use_case,
    overdue_tasks_use_case,
    task_active_status_options,
    task_close_status_options,
    task_priority_options,
    task_status_options,
    tasks_metrics_use_case,
    workflow_domain_options,
)
from web_cabinet.db import init_db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t15_09_summary_use_cases_preserve_operational_counts_and_metrics() -> None:
    conn = _conn()
    try:
        create_alert(
            conn,
            tenant_id="default",
            a=AlertCreate(
                alert_type="health_risk",
                title="High risk",
                source="ml",
                cause="model_flag",
                confidence=0.9,
                object_type="animal",
                object_id="A-1",
                deadline=None,
                owner_user_id=None,
                attachments=[],
                why={"severity": "HIGH"},
                what_to_do=[{"step": "inspect"}],
                data_version="dv_step4",
                scoring_run="score_step4",
                dedupe_key="alert:a-1",
            ),
        )
        create_task(
            conn,
            tenant_id="default",
            t=TaskCreate(
                task_type="qc_followup",
                title="Overdue task",
                domain="qc",
                priority=2,
                due_at="2000-01-01T00:00:00+00:00",
                owner_user_id=None,
                related_alert=None,
                object_type="animal",
                object_id="A-1",
                data_version="dv_step4",
                dedupe_key="task:a-1:overdue",
            ),
        )
        create_task(
            conn,
            tenant_id="default",
            t=TaskCreate(
                task_type="health_visit",
                title="Fresh task",
                domain="health",
                priority=3,
                due_at="2099-01-01T00:00:00+00:00",
                owner_user_id=None,
                related_alert=None,
                object_type="animal",
                object_id="A-2",
                data_version="dv_step4",
                dedupe_key="task:a-2:fresh",
            ),
        )

        snapshot = operational_summary_use_case(conn=conn, tenant_id="default", recent_tasks_limit=10)
        assert int((snapshot.get("alerts") or {}).get("new") or 0) == 1
        assert int((snapshot.get("tasks") or {}).get("open") or 0) >= 2
        assert len(list(snapshot.get("recent_open_tasks") or [])) >= 1

        metrics_payload = tasks_metrics_use_case(conn=conn, tenant_id="default", window_days=30)
        metrics = dict(metrics_payload.get("metrics") or {})
        assert int(metrics_payload.get("active_total") or 0) >= 2
        assert int(metrics.get("active_total") or 0) >= 2
        assert int(metrics.get("active_overdue") or 0) >= 1

        overdue_payload = overdue_tasks_use_case(conn=conn, tenant_id="default", limit=10)
        assert int(overdue_payload.get("count") or 0) >= 1
        assert any(str(item.get("title") or "") == "Overdue task" for item in (overdue_payload.get("items") or []))
    finally:
        conn.close()


def test_t15_09_policy_option_exports_cover_both_uis() -> None:
    assert set(alert_status_options()) == {"acknowledged", "new", "resolved"}
    assert set(task_status_options()) == {"open", "in_progress", "done", "cancelled"}
    assert set(task_active_status_options()) == {"open", "in_progress"}
    assert set(task_close_status_options()) == {"done", "cancelled"}
    assert tuple(task_priority_options()) == (1, 2, 3, 4, 5)
    assert set(workflow_domain_options()) == {"health", "repro", "data", "qc", "econ"}


def test_t15_09_first_party_adapters_use_core_summary_and_option_paths() -> None:
    import web_cabinet.app as appmod

    app_src = inspect.getsource(appmod)
    assert "tasks_metrics_use_case" in app_src
    assert "overdue_tasks_use_case" in app_src
    assert "task_status_options" in app_src

    home_src = Path("streamlit_app/home_v3.py").read_text(encoding="utf-8")
    assert "operational_summary_use_case" in home_src

    alert_src = Path("streamlit_app/pages/5_Alert_Center_v2.py").read_text(encoding="utf-8")
    assert "alert_status_options" in alert_src

    worklist_src = Path("streamlit_app/pages/7_Worklist_v1.py").read_text(encoding="utf-8")
    for needle in [
        "task_status_options",
        "task_active_status_options",
        "task_close_status_options",
        "task_priority_options",
        "workflow_domain_options",
    ]:
        assert needle in worklist_src
