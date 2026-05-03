from __future__ import annotations

from pathlib import Path

from genomeai.feedback_loop import build_feedback_history_dataset, compute_feedback_metrics, load_feedback_config


def test_feedback_history_dataset_and_metrics_capture_revisions() -> None:
    feedback_rows = [
        {
            "feedback_id": "f1",
            "recommendation_id": "rec-1",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "ok",
            "created_at": "2026-03-02T12:00:00Z",
            "recommendation_created_at": "2026-03-02T08:00:00Z",
            "feedback_source": "assistant",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "report_version": "rv_1",
            "scoring_run": "sr_1",
        },
        {
            "feedback_id": "f2",
            "recommendation_id": "rec-1",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "revised",
            "created_at": "2026-03-03T10:00:00Z",
            "recommendation_created_at": "2026-03-02T08:00:00Z",
            "feedback_source": "assistant",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "report_version": "rv_1",
            "scoring_run": "sr_1",
        },
        {
            "feedback_id": "f3",
            "recommendation_id": "rec-2",
            "decision": "accepted",
            "reason_code": "ALREADY_ACTIONED",
            "comment": "done earlier",
            "created_at": "2026-03-04T12:00:00Z",
            "recommendation_created_at": "2026-03-04T11:00:00Z",
            "feedback_source": "alert_center",
            "object_type": "animal",
            "object_id": "1002",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "report_version": "rv_2",
            "scoring_run": "sr_2",
        },
    ]
    cfg = load_feedback_config(Path("configs/feedback/reason_codes.yaml"))

    history = build_feedback_history_dataset(feedback_rows, task_rows=None, cfg=cfg)
    assert len(history) == 3
    rec1 = history[history["recommendation_id"] == "rec-1"].sort_values("feedback_sequence_no")
    assert list(rec1["feedback_sequence_no"].astype(int)) == [1, 2]
    assert rec1.iloc[1]["previous_decision"] == "accepted"
    assert bool(rec1.iloc[1]["decision_changed_from_previous"]) is True
    assert bool(rec1.iloc[1]["recommendation_has_conflict"]) is True
    assert int(rec1.iloc[1]["feedback_events_count"]) == 2

    metrics = compute_feedback_metrics(feedback_rows, task_rows=None, window_days=30, now_utc="2026-03-10T00:00:00Z", cfg=cfg)
    assert metrics["feedback_total"] == 2  # latest labels per recommendation
    assert metrics["feedback_events_total"] == 3  # full history in window
    assert metrics["multi_feedback_recommendations_total"] == 1
    assert metrics["decision_changed_total"] == 1
    assert metrics["decision_changed_rate"] == 0.5
    preview = metrics["recommendation_history_preview"]
    assert preview
    assert preview[0]["recommendation_id"] == "rec-1"
    assert int(preview[0]["feedback_events_count"]) == 2
