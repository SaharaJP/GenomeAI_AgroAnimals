from __future__ import annotations

from streamlit_app.action_flow_ux import (
    build_linked_objects_rows,
    collect_action_flow_bundle,
    compute_action_flow_overview,
)


class _Ctx:
    pass


def test_compute_action_flow_overview_tracks_signal_to_outcome() -> None:
    alert = {
        "alert_id": "a1",
        "alert_type": "QC.MISSING_FIELD",
        "status": "acknowledged",
        "object_type": "dataset",
        "object_id": "dm_animals",
        "confidence": "medium",
    }
    decisions = [{"decision_id": "d1", "action": "recommendation.confirm", "username": "zootech"}]
    tasks = [{"task_id": "t1", "status": "done", "owner_username": "operator", "due_at": "2026-03-29T10:00:00Z", "sla_hours": 24}]
    bundle = {"alert": alert, "decisions": decisions, "tasks": tasks, "facts": [], "object_type": "dataset", "object_id": "dm_animals"}

    overview = compute_action_flow_overview(bundle=bundle, current_kind="task", current_item=tasks[0])

    assert overview.stage_label == "Outcome / closed loop"
    assert overview.owner_label == "operator"
    assert overview.confidence_label == "medium"
    assert overview.linked_counts["decisions"] == 1
    assert overview.linked_counts["tasks"] == 1
    assert overview.steps[-1].state == "done"


def test_build_linked_objects_rows_contains_owner_sla_confidence() -> None:
    bundle = {
        "alert": {"alert_id": "a1", "status": "new", "confidence": "high", "object_type": "animal", "object_id": "1001"},
        "decisions": [{"decision_id": "d1", "action": "alert.acknowledge", "username": "manager", "object_type": "animal", "object_id": "1001"}],
        "tasks": [{"task_id": "t1", "status": "open", "owner_username": "operator", "due_at": "2026-03-30T09:00:00Z", "sla_hours": 8, "object_type": "animal", "object_id": "1001"}],
    }

    rows = build_linked_objects_rows(bundle)

    assert [row["kind"] for row in rows] == ["alert", "decision", "task"]
    assert rows[0]["confidence"] == "high"
    assert rows[1]["owner"] == "manager"
    assert "SLA 8h" in rows[2]["sla"]


def test_collect_action_flow_bundle_merges_related_alert_tasks_and_decisions(monkeypatch) -> None:
    ctx = _Ctx()

    monkeypatch.setattr(
        "streamlit_app.action_flow_ux.get_alert_view",
        lambda ctx, tenant_id, alert_id: {"alert_id": alert_id, "status": "new", "confidence": "low", "object_type": "animal", "object_id": "1001"},
    )
    monkeypatch.setattr(
        "streamlit_app.action_flow_ux.list_decisions_view",
        lambda ctx, tenant_id, **kwargs: [{"decision_id": "d1", "related_alert": kwargs.get("related_alert"), "object_type": "animal", "object_id": "1001"}],
    )
    monkeypatch.setattr(
        "streamlit_app.action_flow_ux.list_tasks_view",
        lambda ctx, tenant_id, **kwargs: [{"task_id": "t1", "related_alert": kwargs.get("related_alert"), "status": "open", "object_type": "animal", "object_id": "1001"}],
    )

    decision = {"decision_id": "d1", "related_alert": "a1", "object_type": "animal", "object_id": "1001"}
    bundle = collect_action_flow_bundle(ctx, tenant_id="default", decision=decision)

    assert bundle["alert"]["alert_id"] == "a1"
    assert bundle["related_alert"] == "a1"
    assert len(bundle["decisions"]) == 1
    assert len(bundle["tasks"]) == 1
