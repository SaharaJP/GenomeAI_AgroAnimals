from __future__ import annotations

import sqlite3
from pathlib import Path

from core.feedback_calibration_v2 import (
    build_feedback_dataset_v2,
    build_feedback_history_dataset_v2,
    build_recalibration_readiness_dataset_v2,
    compute_feedback_metrics_v2,
)
from core.workflow.outcomes import record_completion_outcome_use_case
from core.workflow.tasks import create_task
from core.domain import TaskCreate
from streamlit_app.feedback_capture_v2 import build_feedback_capture_v2_metadata, merge_feedback_metadata
from web_cabinet.db import init_db
from web_cabinet.feedback_v1 import FeedbackCreate, export_feedback_dataset, record_feedback


def test_feedback_calibration_v2_dataset_metrics_capture_override_outcome_and_readiness() -> None:
    feedback_rows = [
        {
            "feedback_id": "f1",
            "recommendation_id": "rec-1",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "accepted with action",
            "created_at": "2026-04-01T12:00:00Z",
            "recommendation_created_at": "2026-04-01T08:00:00Z",
            "task_id": "t-1",
            "feedback_source": "assistant_context.worklist",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "scoring_run": "sr_demo",
            "report_version": "rv_demo",
            "metadata_json": '{"capture_v2": {"context_kind": "worklist", "feedback_kind": "assistant_answer", "override_applied": true, "override_target": "handover", "outcome_status": "done", "outcome_reason_code": "checked", "action_observed_at": "2026-04-01T14:00:00Z"}}',
        },
        {
            "feedback_id": "f2",
            "recommendation_id": "rec-2",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "need more facts",
            "created_at": "2026-04-02T10:00:00Z",
            "recommendation_created_at": "2026-04-02T09:00:00Z",
            "feedback_source": "alert_center",
            "object_type": "group",
            "object_id": "G-1",
            "data_version": "dv_demo",
            "scoring_run": "sr_demo",
            "metadata_json": '{"capture_v2": {"context_kind": "alert", "feedback_kind": "operational_decision", "override_applied": false}}',
        },
    ]
    task_rows = [
        {"task_id": "t-1", "related_alert": "a-1", "object_type": "animal", "object_id": "1001", "status": "done", "closed_reason": "checked", "closed_at": "2026-04-01T14:00:00Z", "updated_at": "2026-04-01T14:00:00Z"},
    ]
    outcome_rows = [
        {"task_id": "t-1", "related_alert": "a-1", "object_type": "animal", "object_id": "1001", "outcome_status": "done", "reason_code": "checked", "created_at": "2026-04-01T14:00:00Z", "linked_decision_id": "d-1", "outcome_role": "zootech"},
    ]

    ds = build_feedback_dataset_v2(feedback_rows, task_rows, outcome_rows)
    assert {"feedback_kind", "feedback_context_kind", "override_applied", "outcome_status", "time_to_action_hours", "recalibration_ready_flag"}.issubset(ds.columns)
    row1 = ds[ds["recommendation_id"] == "rec-1"].iloc[0]
    row2 = ds[ds["recommendation_id"] == "rec-2"].iloc[0]
    assert row1["feedback_kind"] == "assistant_answer"
    assert row1["feedback_context_kind"] == "worklist"
    assert bool(row1["override_applied"]) is True
    assert row1["override_target"] == "handover"
    assert row1["outcome_status"] == "done"
    assert float(row1["time_to_action_hours"]) == 6.0
    assert bool(row1["recalibration_ready_flag"]) is True
    assert bool(row1["recalibration_ready_with_outcome_flag"]) is True
    assert row2["feedback_kind"] == "operational_decision"
    assert row2["feedback_context_kind"] == "alert"
    assert row2["recalibration_readiness_level"] in {"medium", "high"}

    hist = build_feedback_history_dataset_v2(feedback_rows, task_rows, outcome_rows)
    assert "recalibration_readiness_level" in hist.columns

    metrics = compute_feedback_metrics_v2(feedback_rows, task_rows, outcome_rows, window_days=30, now_utc="2026-04-10T00:00:00Z")
    assert metrics["assistant_feedback_total"] == 1
    assert metrics["operational_feedback_total"] == 1
    assert metrics["override_total"] == 1
    assert metrics["outcome_linked_total"] == 1
    assert metrics["recalibration_ready_total"] == 2
    assert metrics["recalibration_ready_with_outcome_total"] == 1
    assert metrics["median_time_to_action_hours"] == 6.0
    assert any(row["feedback_kind"] == "assistant_answer" for row in metrics["by_feedback_kind"])
    assert any(row["feedback_context_kind"] == "worklist" for row in metrics["by_context_kind"])
    assert any(row["outcome_status"] == "done" for row in metrics["by_outcome_status"])
    assert "quality_gaps_breakdown" in metrics

    recal = build_recalibration_readiness_dataset_v2(ds)
    assert len(recal) == 2
    assert "recalibration_readiness_level" in recal.columns


def test_feedback_export_v2_writes_recalibration_dataset_and_metrics(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    task_id = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="check_animal",
            title="Check animal 1001",
            object_type="animal",
            object_id="1001",
            data_version="dv_demo",
            model_version="mv_demo",
            scoring_run="sr_demo",
            report_version="rv_demo",
            priority=2,
            domain="health",
            assignee_team="team-health",
        ),
    )

    meta = merge_feedback_metadata(
        {"source": "pytest"},
        build_feedback_capture_v2_metadata(
            context_kind="worklist",
            feedback_kind="assistant_answer",
            override_applied=True,
            override_target="escalate",
            outcome_status="done",
            outcome_reason_code="checked",
            linked_action="assistant.feedback",
            source_versions={"data_version": "dv_demo", "model_version": "mv_demo", "scoring_run": "sr_demo", "report_version": "rv_demo"},
            action_observed_at="2026-04-03T12:00:00Z",
        ),
    )
    fres = record_feedback(
        conn,
        tenant_id="default",
        fc=FeedbackCreate(
            recommendation_id="rec:assistant:sr_demo:animal:1001",
            decision="accepted",
            reason_code="CONFIRMED_BY_SPECIALIST",
            comment="good",
            related_alert="alert-1",
            task_id=task_id,
            object_type="animal",
            object_id="1001",
            farm_id=None,
            group_id=None,
            data_version="dv_demo",
            model_version="mv_demo",
            report_version="rv_demo",
            qc_run=None,
            scoring_run="sr_demo",
            recommendation_created_at="2026-04-03T08:00:00Z",
            feedback_source="assistant_context.worklist",
            metadata=meta,
        ),
        user_id=2,
        username="zootech",
        created_at="2026-04-03T10:00:00Z",
    )
    assert fres["decision"] == "accepted"

    record_completion_outcome_use_case(
        conn=conn,
        tenant_id="default",
        worklist_id=task_id,
        user_id=2,
        username="zootech",
        role="Operator",
        outcome_status="done",
        reason_code="COMPLETED",
        comment="checked",
    )

    payload = export_feedback_dataset(
        conn,
        artifacts_root=artifacts,
        tenant_id="default",
        feedback_run="fb_run_v2",
        data_version="dv_demo",
    )
    conn.close()

    outputs = payload["outputs"]
    assert Path(outputs["feedback_dataset_csv"]).exists()
    assert Path(outputs["feedback_history_csv"]).exists()
    assert Path(outputs["feedback_recalibration_readiness_csv"]).exists()
    assert Path(outputs["metrics_summary_json"]).exists()
    assert payload["recalibration_rows"] >= 1
    assert "recalibration_dataset_columns" in payload
    assert payload["metrics"]["recalibration_ready_total"] >= 1
    assert payload["metrics"]["outcome_linked_total"] >= 1


def test_feedback_capture_extensions_wired_in_ui_and_docs() -> None:
    helper = Path("streamlit_app/feedback_capture_v2.py").read_text(encoding="utf-8")
    assert "build_feedback_capture_v2_metadata" in helper
    assert "outcome_status_options" in helper

    assistant_ux = Path("streamlit_app/assistant_feedback_ux.py").read_text(encoding="utf-8")
    assert "override_applied=bool(fb_override)" in assistant_ux
    assert "outcome_status=fb_outcome" in assistant_ux
    assert "feedback_kind='assistant_answer'" in assistant_ux

    alert_page = Path("streamlit_app/pages/5_Alert_Center_v2.py").read_text(encoding="utf-8")
    assert 'feedback_kind="operational_decision"' in alert_page
    assert 'Outcome (опционально)' in alert_page

    feedback_page = Path("streamlit_app/pages/23_Feedback_Loop.py").read_text(encoding="utf-8")
    assert 'Preview recalibration readiness dataset' in feedback_page
    assert 'Override rate' in feedback_page
    assert 'Median time-to-action' in feedback_page

    docs = Path("docs/feedback_calibration_loop_v2.md").read_text(encoding="utf-8")
    assert "# T29-03 — feedback → calibration loop v2" in docs
    assert "feedback_recalibration_readiness.csv" in docs

    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")
    assert "## T29-03 — feedback → calibration loop v2" in assumptions
