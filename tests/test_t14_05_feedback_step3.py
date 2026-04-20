from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag
from genomeai.feedback_loop import compute_feedback_metrics, load_feedback_config
from web_cabinet.db import init_db
from web_cabinet.feedback_v1 import FeedbackCreate, record_feedback


def test_feedback_metrics_include_run_breakdowns_and_context_preview() -> None:
    feedback_rows = [
        {
            "feedback_id": "f1",
            "recommendation_id": "rec-1",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "ok",
            "created_at": "2026-03-02T12:00:00Z",
            "recommendation_created_at": "2026-03-02T10:00:00Z",
            "feedback_source": "assistant",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "report_version": "rv_1",
            "scoring_run": "sr_1",
            "task_id": "t1",
        },
        {
            "feedback_id": "f2",
            "recommendation_id": "rec-2",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "weak",
            "created_at": "2026-03-03T12:00:00Z",
            "recommendation_created_at": "2026-03-03T06:00:00Z",
            "feedback_source": "alert_center",
            "object_type": "animal",
            "object_id": "1002",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "report_version": "rv_2",
            "scoring_run": "sr_2",
        },
    ]
    task_rows = [
        {
            "task_id": "t1",
            "related_alert": "alert-1",
            "object_type": "animal",
            "object_id": "1001",
            "status": "done",
            "closed_reason": "checked",
            "closed_at": "2026-03-02T14:00:00Z",
            "updated_at": "2026-03-02T14:00:00Z",
        }
    ]
    cfg = load_feedback_config(Path("configs/feedback/reason_codes.yaml"))
    metrics = compute_feedback_metrics(feedback_rows, task_rows, window_days=30, now_utc="2026-03-10T00:00:00Z", cfg=cfg)

    assert metrics["top_accept_reason_code"] == "CONFIRMED_BY_SPECIALIST"
    assert metrics["top_reject_reason_code"] == "LOW_CONFIDENCE"
    assert metrics["by_scoring_run"][0]["feedback_total"] >= 1
    assert {row["scoring_run"] for row in metrics["by_scoring_run"]} == {"sr_1", "sr_2"}
    assert {row["report_version"] for row in metrics["by_report_version"]} == {"rv_1", "rv_2"}
    assert any(row["decision"] == "accepted" and row["task_status"] == "done" for row in metrics["task_outcomes_by_decision"])
    assert metrics["recommendation_context_preview"][0]["recommendation_id"] in {"rec-1", "rec-2"}


def _write_demo_artifacts(root: Path) -> None:
    kpi_dir = root / "dv_demo" / "runs" / "kpi_run_001" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(json.dumps({"run_id": "kpi_run_001", "kpi_count": 1, "alert_count": 1}, ensure_ascii=False), encoding="utf-8")
    (kpi_dir / "kpi_wide.csv").write_text("farm_id,milk_kg\nfarm_1,123.4\n", encoding="utf-8")
    (kpi_dir / "kpi_alerts.csv").write_text("alert_id,severity,farm_id\nalert_1,high,farm_1\n", encoding="utf-8")



def test_answer_question_rag_summarizes_feedback_loop(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)
    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    record_feedback(
        conn,
        tenant_id="default",
        fc=FeedbackCreate(
            recommendation_id="rec:assistant:sr_demo:animal:1002",
            decision="rejected",
            reason_code="LOW_CONFIDENCE",
            comment="too weak",
            related_alert="alert_2",
            task_id=None,
            object_type="animal",
            object_id="1002",
            farm_id=None,
            group_id=None,
            data_version="dv_demo",
            model_version="mv_demo",
            report_version="rv_demo",
            qc_run=None,
            scoring_run="sr_demo",
            recommendation_created_at="2026-03-02T10:00:00Z",
            feedback_source="assistant",
            metadata={"source": "pytest"},
        ),
        user_id=2,
        username="zootech",
        created_at="2026-03-03T10:00:00Z",
    )
    conn.close()

    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="почему отклоняют рекомендации по scoring_run sr_demo",
        web_db_path=db_path,
        use_llm=False,
        user_permissions=["tasks.view", "decisionlog.view"],
    )
    assert "Tool route: query_tasks" in res.answer
    assert "Feedback loop по рекомендациям:" in res.answer
    assert "LOW_CONFIDENCE" in res.answer
    assert "scoring_run=sr_demo" in res.answer or "По scoring_run:" in res.answer
    assert "[Источник:" in res.answer
