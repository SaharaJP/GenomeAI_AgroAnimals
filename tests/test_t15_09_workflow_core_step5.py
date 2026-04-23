from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from core.workflow import (
    TaskCreate,
    create_task,
    workflow_default_stage,
    workflow_listing_use_case,
    workflow_stage_catalog,
    workflow_stage_keys,
    workflow_stage_options,
    workflow_team_catalog,
    workflow_team_keys,
)
from web_cabinet.db import init_db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t15_09_stage_and_team_catalogs_are_loaded_from_core_with_legacy_defaults() -> None:
    stages = workflow_stage_catalog()
    assert str(stages.get("default_stage_open") or "")
    assert list(stages.get("stages") or [])
    assert tuple(stages.get("stage_keys") or ()) == workflow_stage_keys()
    assert workflow_default_stage() in workflow_stage_keys()
    assert workflow_stage_options(include_blank=True)[0] == ""

    teams = workflow_team_catalog()
    assert isinstance(list(teams.get("teams") or []), list)
    assert tuple(teams.get("team_keys") or ()) == workflow_team_keys()
    assert workflow_team_keys(include_blank=True)[0] == ""


def test_t15_09_workflow_listing_use_case_returns_filters_and_stage_options_from_core() -> None:
    conn = _conn()
    try:
        create_task(
            conn,
            tenant_id="default",
            t=TaskCreate(
                task_type="health_visit",
                title="Inspect cow A-1",
                domain="health",
                priority=2,
                due_at="2099-01-01T00:00:00+00:00",
                owner_user_id=None,
                related_alert=None,
                object_type="animal",
                object_id="A-1",
                data_version="dv_step5",
                dedupe_key="task:a-1:step5",
            ),
        )
        listing = workflow_listing_use_case(
            conn=conn,
            tenant_id="default",
            status="open",
            task_type="health_visit",
            stage="",
            q="Inspect",
            limit=50,
            offset=0,
        )
        assert int(listing.get("total") or 0) == 1
        assert len(list(listing.get("tasks") or [])) == 1
        assert getattr(listing.get("filters"), "status", None) == "open"
        assert getattr(listing.get("filters"), "task_type", None) == "health_visit"
        assert getattr(listing.get("filters"), "q", None) == "Inspect"
        assert list(listing.get("stage_options") or [])[0] == ""
        assert workflow_default_stage() in tuple(listing.get("stage_options") or ())
    finally:
        conn.close()


def test_t15_09_first_party_adapters_use_core_catalog_and_listing_paths() -> None:
    import web_cabinet.app as appmod

    app_src = inspect.getsource(appmod)
    for needle in [
        "workflow_team_catalog",
        "workflow_stage_catalog",
        "workflow_listing_use_case",
    ]:
        assert needle in app_src

    template_src = Path("web_cabinet/templates/workflow.html").read_text(encoding="utf-8")
    assert "stage_options" in template_src
    assert '<select name="stage">' in template_src

    worklist_src = Path("streamlit_app/pages/7_Worklist_v1.py").read_text(encoding="utf-8")
    for needle in [
        "workflow_stage_keys",
        "workflow_default_stage",
        "workflow_team_keys",
    ]:
        assert needle in worklist_src
