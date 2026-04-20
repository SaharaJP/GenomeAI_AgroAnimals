from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from core.infra import (
    AlertsRepo,
    ArtifactsRepo,
    AuditRepo,
    ConnectorRunsRepo,
    DecisionsRepo,
    FeedbackRepo,
    FavoritesRepo,
    PlaybooksRepo,
    ReportApprovalsRepo,
    ReportTemplatesRepo,
    RunsRepo,
    SavedViewsRepo,
    TasksRepo,
    WeeklyPlansRepo,
    WhatIfReportsRepo,
    WhatIfScenariosRepo,
    resolve_db_backend,
    resolve_db_config,
)
from web_cabinet.alerts_v2 import AlertCreate, create_alert
from web_cabinet.audit import write_audit
from web_cabinet.db import connect, create_job, get_settings, init_db
from web_cabinet.decision_log_v2 import DecisionCreate, append_decision
from web_cabinet.tasks_v1 import TaskCreate, create_task


def _mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t15_04_db_backend_is_configurable_with_sqlite_default_and_postgres_interface() -> None:
    cfg = resolve_db_config()
    assert cfg.backend == "sqlite"
    assert resolve_db_backend().name == "sqlite"
    assert resolve_db_config(backend="postgres", dsn="postgresql://demo").backend == "postgres"
    assert resolve_db_backend(backend="postgres", dsn="postgresql://demo").name == "postgres"



def test_t15_04_core_infra_repositories_support_sqlite_in_memory_crud() -> None:
    conn = _mem_conn()

    alert_id = create_alert(
        conn,
        tenant_id="default",
        a=AlertCreate(
            alert_type="qc_error",
            title="QC issue",
            source="qc",
            cause="missing field",
            confidence=0.8,
            object_type="animal",
            object_id="1001",
            deadline=None,
            owner_user_id=None,
            attachments=[],
            why={},
            what_to_do=[],
            dedupe_key="alert_dk_1",
        ),
    )
    task_id = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="qc_fix",
            title="Fix QC",
            domain="qc",
            priority=2,
            related_alert=alert_id,
            object_type="animal",
            object_id="1001",
            dedupe_key="task_dk_1",
        ),
    )
    decision_id = append_decision(
        conn,
        tenant_id="default",
        d=DecisionCreate(
            recommendation_id="rec_1",
            action="recommendation.accepted",
            user_id=1,
            username="admin",
            reason="CONFIRMED_BY_MANAGER",
            comment="ok",
            related_alert=alert_id,
            object_type="animal",
            object_id="1001",
            farm_id="farm_1",
            group_id=None,
            data_version="dv1",
            model_version="mv1",
            report_version="rv1",
            qc_run="qc1",
            scoring_run="sr1",
            metadata={"task_id": task_id},
        ),
    )
    audit_id = write_audit(
        conn,
        tenant_id="default",
        user_id=1,
        username="admin",
        role="admin",
        action="tasks_v1.create",
        object_type="task",
        object_id=task_id,
        data_version="dv1",
        run_id="sr1",
        after={"task_id": task_id},
    )

    alerts_repo = AlertsRepo(conn)
    tasks_repo = TasksRepo(conn)
    decisions_repo = DecisionsRepo(conn)
    audit_repo = AuditRepo(conn)

    assert alerts_repo.get(tenant_id="default", alert_id=alert_id)["alert_id"] == alert_id
    listed_alerts = alerts_repo.list(tenant_id="default", filters={"status": "new"}, limit=50, offset=0)
    assert listed_alerts["total"] >= 1
    assert listed_alerts["alerts"][0]["why"] == {}

    task_row = tasks_repo.get_row(tenant_id="default", task_id=task_id)
    assert task_row is not None
    assert task_row["status"] == "open"
    assert tasks_repo.exists_active_dedupe(tenant_id="default", dedupe_key="task_dk_1") is True
    listed_tasks = tasks_repo.list_rows(tenant_id="default", filters={"status": "open"}, limit=50, offset=0)
    assert listed_tasks["total"] >= 1

    decision = decisions_repo.get(tenant_id="default", decision_id=decision_id)
    assert decision is not None
    assert decision["metadata"] == {"task_id": task_id}
    decisions = decisions_repo.list(tenant_id="default", filters={"object_id": "1001"}, limit=50, offset=0)
    assert decisions["total"] >= 1

    feedback_repo = FeedbackRepo(conn)
    feedback_id = feedback_repo.insert_event(
        tenant_id="default",
        feedback_id="fb_1",
        created_at="2026-03-14T10:10:00+00:00",
        recommendation_id="rec_1",
        decision="accepted",
        reason_code="validated",
        comment="ok",
        recommendation_created_at="2026-03-14T10:00:00+00:00",
        decision_seconds=600,
        related_alert=alert_id,
        task_id=task_id,
        object_type="animal",
        object_id="1001",
        farm_id="farm_1",
        group_id=None,
        data_version="dv1",
        model_version="mv1",
        report_version="rv1",
        qc_run="qc1",
        scoring_run="sr1",
        feedback_source="feedback_ui",
        decision_id=decision_id,
        metadata={"source": "test"},
    )
    feedback = feedback_repo.list_events(tenant_id="default", filters={"recommendation_id": "rec_1"}, limit=10, offset=0)
    assert feedback_id == "fb_1"
    assert feedback["total"] >= 1
    assert feedback["items"][0]["metadata"] == {"source": "test"}

    audit_rows = audit_repo.list_rows(select_sql="SELECT * FROM audit_log WHERE id=?", args=[audit_id])
    assert audit_rows[0]["action"] == "tasks_v1.create"



def test_t15_04_runs_repo_and_artifacts_repo_support_file_backed_storage(tmp_path: Path) -> None:
    project_root = Path.cwd()
    db_path = tmp_path / "web.db"
    conn = connect(db_path)
    init_db(conn)

    log_path = tmp_path / "logs" / "job.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    job_id = create_job(
        conn,
        kind="qc",
        user="admin",
        tenant_id="default",
        user_id=1,
        command="python -m genomeai.cli qc",
        args={"data_version": "dv1", "qc_run": "qc1"},
        log_path=log_path,
    )

    runs_repo = RunsRepo(conn)
    job = runs_repo.get_job(job_id)
    assert job is not None
    listed = runs_repo.list_jobs_filtered(status="queued", limit=20)
    assert any(int(item["id"]) == int(job_id) for item in listed)
    assert runs_repo.list_job_family(job_id)[0]["id"] == job_id

    artifacts_root = tmp_path / "artifacts"
    storage_root = tmp_path / "storage"
    repo = ArtifactsRepo(project_root=project_root, artifacts_root=artifacts_root, storage_root=storage_root)
    payload_path = artifacts_root / "system" / "feedback" / "run_1" / "manifest.json"
    repo.write_json(payload_path, {"ok": True, "job_id": job_id})
    resolved, virtual = repo.resolve_virtual_path(f"artifacts/{payload_path.relative_to(artifacts_root).as_posix()}")
    assert resolved == payload_path.resolve()
    assert virtual.startswith("artifacts/")
    assert repo.read_json_virtual(virtual)["job_id"] == job_id
    assert repo.list_files_recursive(payload_path.parent, limit=10)[0].name == "manifest.json"
    preview_text, preview_truncated = repo.read_preview(payload_path, max_bytes=1024)
    assert '"job_id"' in preview_text
    assert preview_truncated is False
    tail = repo.read_bytes_tail(log_path, max_bytes=8)
    assert tail["size_bytes"] >= tail["tail_bytes"]
    stream = repo.read_stream(log_path, cursor=0, max_bytes=5)
    assert stream["next_cursor"] > 0
    preview, truncated = repo.preview_virtual(virtual, max_bytes=1024)
    assert '"ok": true' in preview.lower()
    assert truncated is False




def test_t15_04_playbooks_and_connector_repos_preserve_sqlite_behavior(tmp_path: Path) -> None:
    conn = _mem_conn()

    playbooks_repo = PlaybooksRepo(conn)
    version_id = playbooks_repo.create_version(
        tenant_id="default",
        version_id="pbv_1",
        playbook_key="alert:ML.MASTITIS_RISK",
        target_kind="alert",
        target_type="ML.MASTITIS_RISK",
        farm_id="F1",
        name="PB",
        description="demo",
        steps=[{"key": "s1", "title": "Шаг 1", "required": True}],
        created_at="2026-03-14T10:00:00+00:00",
        created_by=1,
        created_by_username="admin",
        comment="seed",
    )
    playbooks_repo.set_active_version(
        tenant_id="default",
        playbook_key="alert:ML.MASTITIS_RISK",
        farm_id="F1",
        version_id=version_id,
        updated_at="2026-03-14T10:01:00+00:00",
    )
    assert playbooks_repo.get_version(tenant_id="default", version_id=version_id)["steps"][0]["title"] == "Шаг 1"
    assert playbooks_repo.get_active_version_mapping(tenant_id="default", playbook_key="alert:ML.MASTITIS_RISK", farm_id="F1")["active_version_id"] == version_id

    connector_repo = ConnectorRunsRepo(conn)
    connector_repo.ensure_tables()
    create_job(
        conn,
        kind="connector_run",
        user="operator",
        tenant_id="default",
        user_id=2,
        command="python -m genomeai",
        args={"argv": ["connectors", "run", "--config", str((tmp_path / "demo.yaml").resolve()), "--trigger", "manual", "--connector-run-id", "cr_queued", "--datasets", "animals"]},
        log_path=tmp_path / "logs" / "connector.log",
    )
    connector_repo.start_run(
        tenant_id="default",
        connector_run_id="cr_1",
        connector_id="demo",
        kind="file",
        trigger_type="manual",
        schedule_slot=None,
        config_path=str((tmp_path / "demo.yaml").resolve()),
        started_at="2026-03-14T10:00:00+00:00",
    )
    connector_repo.finish_run(
        tenant_id="default",
        connector_run_id="cr_1",
        status="success",
        finished_at="2026-03-14T10:05:00+00:00",
        data_version="dv_1",
        message="ok",
        outputs={"written": 1},
        selected_files=[{"dataset_key": "animals"}],
        ingest_summaries=[],
    )
    got = connector_repo.get_run(tenant_id="default", connector_run_id="cr_1")
    assert got is not None
    assert got["outputs"]["written"] == 1
    listed = connector_repo.list_runs(tenant_id="default", connector_id="demo", limit=10)
    assert listed[0]["connector_run_id"] == "cr_1"
    pending = connector_repo.list_pending_jobs(tenant_id="default", config_path=str((tmp_path / "demo.yaml").resolve()), limit=10, parser=lambda argv: {"config_path": argv[3], "trigger_type": "manual", "connector_run_id": "cr_queued", "dataset_keys": ["animals"]})
    assert pending and pending[0]["connector_run_id"] == "cr_queued"




def test_t15_04_personalization_repos_preserve_sqlite_behavior() -> None:
    conn = _mem_conn()

    favorites_repo = FavoritesRepo(conn)
    favorites_repo.add(
        tenant_id="default",
        user_id=1,
        object_type="animal",
        object_id="A1",
        created_at="2026-03-14T10:00:00+00:00",
        label="Animal A1",
        metadata={"source": "test"},
    )
    favorites_repo.add(
        tenant_id="default",
        user_id=1,
        object_type="animal",
        object_id="A1",
        created_at="2026-03-14T10:01:00+00:00",
        label="Animal A1",
        metadata={"source": "duplicate"},
    )
    assert favorites_repo.exists(tenant_id="default", user_id=1, object_type="animal", object_id="A1") is True
    favs = favorites_repo.list(tenant_id="default", user_id=1, limit=10)
    assert len(favs) == 1
    assert favs[0]["metadata"] == {"source": "test"}

    saved_views_repo = SavedViewsRepo(conn)
    saved_views_repo.create(
        view_id="view_1",
        tenant_id="default",
        created_at="2026-03-14T10:00:00+00:00",
        updated_at="2026-03-14T10:00:00+00:00",
        created_by=1,
        created_by_username="admin",
        scope="shared",
        name="Main View",
        description="demo",
        page_key="kpi_drilldown",
        state={"kpi_drilldown.kpi_id": "milk_total_kg_7d"},
        data_version="dv1",
        run_id="run1",
    )
    view = saved_views_repo.get(tenant_id="default", view_id="view_1")
    assert view is not None
    assert view["state"]["kpi_drilldown.kpi_id"] == "milk_total_kg_7d"
    listed_views = saved_views_repo.list(tenant_id="default", user_id=2, page_key="kpi_drilldown", include_shared=True, limit=10)
    assert listed_views and listed_views[0]["view_id"] == "view_1"
    saved_views_repo.update(
        tenant_id="default",
        view_id="view_1",
        updated_at="2026-03-14T10:05:00+00:00",
        name="Main View v2",
        description="updated",
        scope="shared",
        state_json='{"kpi_drilldown.kpi_id":"SCC_mean_7d"}',
        data_version="dv2",
        run_id="run2",
    )
    assert saved_views_repo.get(tenant_id="default", view_id="view_1")["state"]["kpi_drilldown.kpi_id"] == "SCC_mean_7d"

    templates_repo = ReportTemplatesRepo(conn)
    templates_repo.create(
        template_id="tpl_1",
        tenant_id="default",
        created_at="2026-03-14T10:00:00+00:00",
        updated_at="2026-03-14T10:00:00+00:00",
        created_by=1,
        created_by_username="admin",
        scope="user",
        name="Template",
        description="demo",
        sections_json='["kpi_summary"]',
        metrics_json='["milk_total_kg_7d"]',
        options_json='{"role":"director"}',
    )
    tpl = templates_repo.get(tenant_id="default", template_id="tpl_1")
    assert tpl is not None
    assert tpl["sections"] == ["kpi_summary"]
    assert tpl["options"] == {"role": "director"}
    templates_repo.update(
        tenant_id="default",
        template_id="tpl_1",
        updated_at="2026-03-14T10:06:00+00:00",
        scope="shared",
        name="Template v2",
        description="updated",
        sections_json='["alerts"]',
        metrics_json='["SCC_mean_7d"]',
        options_json='{"role":"zootech"}',
    )
    listed_templates = templates_repo.list(tenant_id="default", user_id=2, include_shared=True, limit=10)
    assert listed_templates and listed_templates[0]["name"] == "Template v2"


def test_t15_04_weekly_whatif_and_report_approval_repos_preserve_sqlite_behavior(tmp_path: Path) -> None:
    conn = _mem_conn()

    weekly_repo = WeeklyPlansRepo(conn)
    plan_id = weekly_repo.create(
        plan_id="plan_1",
        tenant_id="default",
        created_at="2026-03-14T10:00:00+00:00",
        updated_at="2026-03-14T10:00:00+00:00",
        week_start="2026-03-09",
        name="Weekly plan",
        summary="demo",
        status="draft",
        farm_id="farm_1",
        data_version="dv_1",
        action_items=[{"key": "a1", "title": "Do thing"}],
        created_by=1,
        created_by_username="admin",
    )
    assert weekly_repo.get(tenant_id="default", plan_id=plan_id)["action_items"][0]["title"] == "Do thing"
    assert weekly_repo.list(tenant_id="default", status="draft", q=None, limit=10, offset=0)["total"] == 1
    weekly_repo.request_approval(
        tenant_id="default",
        plan_id=plan_id,
        requested_at="2026-03-14T10:01:00+00:00",
        requested_by=1,
        requested_by_username="admin",
        comment="please review",
    )
    assert weekly_repo.list_pending_approval(tenant_id="default", limit=10, offset=0)["total"] == 1
    weekly_repo.link_task(tenant_id="default", plan_id=plan_id, action_key="a1", task_id="task_1", created_at="2026-03-14T10:02:00+00:00")
    weekly_repo.approve(
        tenant_id="default",
        plan_id=plan_id,
        updated_at="2026-03-14T10:03:00+00:00",
        approved_by=2,
        approved_by_username="director",
        comment="ok",
        tasks_created_at="2026-03-14T10:03:00+00:00",
        tasks_created_run_id="run_1",
    )
    assert weekly_repo.list_task_links(tenant_id="default", plan_id=plan_id) == {"a1": "task_1"}

    scenarios_repo = WhatIfScenariosRepo(conn)
    scenario_id = scenarios_repo.create(
        scenario_id="sc_1",
        tenant_id="default",
        created_at="2026-03-14T10:00:00+00:00",
        updated_at="2026-03-14T10:00:00+00:00",
        name="Scenario",
        description="demo",
        status="draft",
        created_by=1,
        created_by_username="analyst",
        data_version="dv_1",
        params={"milk_price": 42},
    )
    assert scenarios_repo.get(tenant_id="default", scenario_id=scenario_id)["params"]["milk_price"] == 42
    scenarios_repo.attach_last_run(tenant_id="default", scenario_id=scenario_id, updated_at="2026-03-14T10:05:00+00:00", economics_run="econ_1")
    scenarios_repo.approve(tenant_id="default", scenario_id=scenario_id, updated_at="2026-03-14T10:06:00+00:00", approved_by=2, approved_by_username="director", comment="ok")
    assert scenarios_repo.list(tenant_id="default", status="approved", q=None, limit=10, offset=0)["total"] == 1

    reports_repo = WhatIfReportsRepo(conn)
    reports_repo.create(
        tenant_id="default",
        created_at="2026-03-14T10:07:00+00:00",
        created_by=1,
        created_by_username="analyst",
        scenario_id=scenario_id,
        report_version="wr_1",
        data_version="dv_1",
        base_economics_run="econ_base",
        scenario_economics_run="econ_1",
        pdf_rel_path="artifacts/dv_1/whatif/wr_1/report.pdf",
        params={"delta": 100},
    )
    assert reports_repo.get(tenant_id="default", report_version="wr_1")["params"]["delta"] == 100

    approvals_repo = ReportApprovalsRepo(conn)
    approvals_repo.ensure_row(tenant_id="default", data_version="dv_1", report_version="report_1", now="2026-03-14T10:08:00+00:00")
    approvals_repo.approve(tenant_id="default", data_version="dv_1", report_version="report_1", updated_at="2026-03-14T10:09:00+00:00", user_id=2, username="director", comment="approved")
    assert approvals_repo.get(tenant_id="default", data_version="dv_1", report_version="report_1")["status"] == "approved"





def test_t15_04_web_db_bootstrap_is_moved_to_core_infra_with_legacy_shim() -> None:
    import web_cabinet.db as legacy_db
    import core.infra.web_db as core_web_db

    legacy_src = inspect.getsource(legacy_db)
    assert "conn.execute(" not in legacy_src
    assert "core.infra.web_db" in legacy_src
    assert legacy_db.init_db is core_web_db.init_db
    assert legacy_db.connect is core_web_db.connect
    assert legacy_db.get_settings is core_web_db.get_settings

def test_t15_04_web_modules_delegate_storage_access_to_core_infra_repositories() -> None:
    import web_cabinet.alerts_v2 as alerts_mod
    import web_cabinet.audit as audit_mod
    import web_cabinet.decision_log_v2 as decisions_mod
    import web_cabinet.tasks_v1 as tasks_mod
    import web_cabinet.playbooks_v1 as playbooks_mod
    import web_cabinet.connectors_v1 as connectors_mod
    import web_cabinet.feedback_v1 as feedback_mod
    import web_cabinet.favorites as favorites_mod
    import web_cabinet.jobs_v2 as jobs_mod
    import web_cabinet.report_templates as report_templates_mod
    import web_cabinet.reports_approvals_v1 as report_approvals_mod
    import web_cabinet.saved_views as saved_views_mod
    import web_cabinet.weekly_plans_v1 as weekly_plans_mod
    import web_cabinet.whatif_reports_v1 as whatif_reports_mod
    import web_cabinet.whatif_scenarios_v1 as whatif_scenarios_mod
    import web_cabinet.app as app_mod

    assert "conn.execute(" not in inspect.getsource(alerts_mod)
    assert "conn.execute(" not in inspect.getsource(decisions_mod)
    assert "conn.execute(" not in inspect.getsource(tasks_mod)
    assert "conn.execute(" not in inspect.getsource(audit_mod)
    assert "conn.execute(" not in inspect.getsource(playbooks_mod)
    assert "conn.execute(" not in inspect.getsource(connectors_mod)
    assert "conn.execute(" not in inspect.getsource(feedback_mod)
    assert ".read_text(" not in inspect.getsource(playbooks_mod)
    assert ".open(" not in inspect.getsource(connectors_mod)
    assert "conn.execute(" not in inspect.getsource(favorites_mod)
    assert "conn.execute(" not in inspect.getsource(saved_views_mod)
    assert "conn.execute(" not in inspect.getsource(report_templates_mod)
    assert "conn.execute(" not in inspect.getsource(report_approvals_mod)
    assert "conn.execute(" not in inspect.getsource(weekly_plans_mod)
    assert "conn.execute(" not in inspect.getsource(whatif_reports_mod)
    assert "conn.execute(" not in inspect.getsource(whatif_scenarios_mod)
    assert ".read_text(" not in inspect.getsource(weekly_plans_mod)
    jobs_src = inspect.getsource(jobs_mod)
    assert ".read_text(" not in jobs_src
    assert ".read_bytes(" not in jobs_src
    assert ".rglob(" not in jobs_src
    app_src = inspect.getsource(app_mod)
    assert "RunsRepo(" in app_src
    assert "ArtifactsRepo(" in app_src
    assert "conn.execute(" not in app_src
