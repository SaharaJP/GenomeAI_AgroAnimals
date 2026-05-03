from __future__ import annotations

from pathlib import Path

from genomeai.feedback_loop import build_feedback_dataset, compute_feedback_metrics, load_feedback_config, validate_feedback_payload


def test_feedback_core_builds_latest_dataset_and_metrics() -> None:
    feedback_rows = [
        {
            "feedback_id": "f1",
            "recommendation_id": "rec-1",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "early",
            "created_at": "2026-03-01T12:00:00Z",
            "recommendation_created_at": "2026-03-01T10:00:00Z",
            "related_alert": "a-1",
            "task_id": None,
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "scoring_run": "sr1",
        },
        {
            "feedback_id": "f2",
            "recommendation_id": "rec-1",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "latest",
            "created_at": "2026-03-02T12:00:00Z",
            "recommendation_created_at": "2026-03-01T10:00:00Z",
            "related_alert": "a-1",
            "task_id": None,
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "scoring_run": "sr1",
        },
        {
            "feedback_id": "f3",
            "recommendation_id": "rec-2",
            "decision": "rejected",
            "reason_code": "FALSE_POSITIVE",
            "comment": "other",
            "created_at": "2026-03-03T12:00:00Z",
            "recommendation_created_at": "2026-03-03T06:00:00Z",
            "related_alert": "a-2",
            "task_id": "t-2",
            "object_type": "animal",
            "object_id": "1002",
            "data_version": "dv_demo",
            "scoring_run": "sr1",
        },
    ]
    task_rows = [
        {"task_id": "t-2", "related_alert": "a-2", "object_type": "animal", "object_id": "1002", "status": "done", "closed_reason": "checked", "closed_at": "2026-03-03T15:00:00Z", "updated_at": "2026-03-03T15:00:00Z"},
    ]

    ds = build_feedback_dataset(feedback_rows, task_rows, latest_only=True)
    assert list(ds["recommendation_id"]) == ["rec-1", "rec-2"]
    assert list(ds["decision"]) == ["accepted", "rejected"]
    assert ds.loc[ds["recommendation_id"] == "rec-2", "task_status"].iloc[0] == "done"

    metrics = compute_feedback_metrics(feedback_rows, task_rows, window_days=30, now_utc="2026-03-10T00:00:00Z")
    assert metrics["feedback_total"] == 2
    assert metrics["accepted_total"] == 1
    assert metrics["rejected_total"] == 1
    assert metrics["acceptance_rate"] == 0.5
    assert metrics["task_outcomes"]["done"] == 1


def test_feedback_config_and_validation() -> None:
    cfg = load_feedback_config(Path("configs/feedback/reason_codes.yaml"))
    assert "LOW_CONFIDENCE" in cfg.rejected_codes
    validate_feedback_payload(decision="accepted", reason_code="CONFIRMED_BY_SPECIALIST", cfg=cfg)
