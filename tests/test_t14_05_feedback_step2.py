from __future__ import annotations

from pathlib import Path

from genomeai.feedback_loop import build_feedback_dataset, compute_feedback_metrics, load_feedback_config


def test_feedback_dataset_contains_training_columns_and_breakdowns() -> None:
    feedback_rows = [
        {
            "feedback_id": "f1",
            "recommendation_id": "rec-1",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "accepted",
            "created_at": "2026-03-02T12:00:00Z",
            "recommendation_created_at": "2026-03-02T08:00:00Z",
            "related_alert": "a-1",
            "task_id": "t-1",
            "feedback_source": "assistant",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "scoring_run": "sr1",
        },
        {
            "feedback_id": "f2",
            "recommendation_id": "rec-2",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "not sure",
            "created_at": "2026-03-03T12:00:00Z",
            "recommendation_created_at": "2026-03-03T00:00:00Z",
            "related_alert": "a-2",
            "task_id": None,
            "feedback_source": "alert_center",
            "object_type": "group",
            "object_id": "G-1",
            "data_version": "dv_demo",
            "scoring_run": "sr1",
        },
    ]
    task_rows = [
        {"task_id": "t-1", "related_alert": "a-1", "object_type": "animal", "object_id": "1001", "status": "done", "closed_reason": "checked", "closed_at": "2026-03-02T14:00:00Z", "updated_at": "2026-03-02T14:00:00Z"},
    ]
    cfg = load_feedback_config(Path("configs/feedback/reason_codes.yaml"))

    ds = build_feedback_dataset(feedback_rows, task_rows, latest_only=True, cfg=cfg)
    assert {"feedback_target_label", "feedback_sample_weight", "task_outcome_label", "has_task_link", "has_task_outcome"}.issubset(ds.columns)
    row_ok = ds[ds["recommendation_id"] == "rec-1"].iloc[0]
    row_bad = ds[ds["recommendation_id"] == "rec-2"].iloc[0]
    assert int(row_ok["feedback_target_label"]) == 1
    assert float(row_ok["feedback_sample_weight"]) > 1.0
    assert int(row_ok["task_outcome_label"]) == 1
    assert bool(row_ok["has_task_link"]) is True
    assert int(row_bad["feedback_target_label"]) == 0
    assert float(row_bad["feedback_sample_weight"]) < 1.0

    metrics = compute_feedback_metrics(feedback_rows, task_rows, window_days=30, now_utc="2026-03-10T00:00:00Z", cfg=cfg)
    assert metrics["feedback_total"] == 2
    assert metrics["task_linked_total"] == 1
    assert metrics["task_linked_rate"] == 0.5
    assert metrics["task_outcome_known_rate"] == 0.5
    assert metrics["by_feedback_source"][0]["feedback_total"] >= 1
    assert metrics["by_object_type"][0]["feedback_total"] >= 1
    assert sum(int(x["count"]) for x in metrics["decision_time_buckets"]) == 2
