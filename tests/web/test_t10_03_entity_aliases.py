from __future__ import annotations

import sqlite3

from web_cabinet.db import init_db
from web_cabinet.decision_log_v2 import DecisionCreate, append_decision, list_decisions_for_object
from web_cabinet.tasks_v1 import TaskCreate, create_task, list_tasks_for_object


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_tasks_alias_pen_is_visible_in_group_listing() -> None:
    conn = _conn()
    try:
        tid = create_task(
            conn,
            tenant_id="default",
            t=TaskCreate(task_type="x", title="t1", object_type="pen", object_id="PEN_01"),
        )
        assert tid

        res = list_tasks_for_object(conn, tenant_id="default", object_type="group", object_id="PEN_01")
        assert res["total"] == 1
        assert len(res["tasks"]) == 1
        assert res["tasks"][0]["object_id"] == "PEN_01"
    finally:
        conn.close()


def test_decisions_alias_pen_is_visible_in_group_listing() -> None:
    conn = _conn()
    try:
        did = append_decision(
            conn,
            tenant_id="default",
            d=DecisionCreate(
                recommendation_id=None,
                action="recommendation.confirm",
                user_id=1,
                username="u",
                reason="r",
                comment=None,
                related_alert=None,
                object_type="pen",
                object_id="PEN_02",
                farm_id=None,
                group_id=None,
                data_version="dv_demo",
                model_version=None,
                report_version=None,
                qc_run=None,
                scoring_run=None,
                metadata={"k": "v"},
            ),
        )
        assert did

        res = list_decisions_for_object(conn, tenant_id="default", object_type="group", object_id="PEN_02")
        assert res["total"] == 1
        assert len(res["decisions"]) == 1
        assert res["decisions"][0]["object_id"] == "PEN_02"
    finally:
        conn.close()
