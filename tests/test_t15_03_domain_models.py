from __future__ import annotations

import importlib
import sys
import warnings
from datetime import date
from pathlib import Path

from genomeai.feedback_loop import load_feedback_config

from core.domain import (
    Alert,
    AlertCreate,
    AlertSeverity,
    Decision,
    DecisionRecord,
    Event,
    EventSeverity,
    RecommendationDecision,
    RunMeta,
    TaskCreate,
    DEFAULT_ACCEPTED_REASON_CODES,
    DEFAULT_REJECTED_REASON_CODES,
    canonical_model_to_legacy_dict,
    normalize_task_active_status_for_update,
    normalize_task_close_status,
    reason_codes_for_feedback_decision,
    require_draft_approval_status,
    validate_feedback_decision_and_reason,
    decision_record_to_legacy_dict,
    run_meta_to_legacy_dict,
    task_from_row,
    task_to_api_dict,
)


def test_t15_03_legacy_target_model_import_warns_and_points_to_core_module() -> None:
    sys.modules.pop("genomeai.target.model_v2", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy_mod = importlib.import_module("genomeai.target.model_v2")

    core_mod = importlib.import_module("core.domain.target_models")
    assert legacy_mod.__file__ == core_mod.__file__
    assert legacy_mod.__name__ == "core.domain.target_models"
    assert any(
        item.category is DeprecationWarning
        and "genomeai.target.model_v2 is deprecated" in str(item.message)
        for item in caught
    )


def test_t15_03_legacy_target_lactation_validation_preserved() -> None:
    mod = importlib.import_module("genomeai.target.model_v2")
    Lactation = mod.Lactation

    ok = Lactation(
        lactation_id="lac_1",
        animal_id="cow_1",
        lactation_no=1,
        calving_date=date(2025, 1, 10),
        dryoff_date=date(2025, 12, 1),
    )
    assert ok.lactation_id == "lac_1"

    try:
        Lactation(
            lactation_id="lac_bad",
            animal_id="cow_1",
            lactation_no=1,
            calving_date=date(2025, 1, 10),
            dryoff_date=date(2025, 1, 1),
        )
    except Exception as exc:
        assert "dryoff_date must be >= calving_date" in str(exc)
    else:  # pragma: no cover - must fail
        raise AssertionError("Lactation validation drifted")


def test_t15_03_task_and_alert_create_are_shared_core_models() -> None:
    from web_cabinet.alerts_v2 import AlertCreate as WebAlertCreate
    from web_cabinet.tasks_v1 import TaskCreate as WebTaskCreate

    assert WebTaskCreate is TaskCreate
    assert WebAlertCreate is AlertCreate


def test_t15_03_task_adapter_preserves_legacy_api_shape() -> None:
    row = {
        "task_id": "task_1",
        "tenant_id": "default",
        "created_at": "2026-03-13T10:00:00+00:00",
        "updated_at": "2026-03-13T10:05:00+00:00",
        "task_type": "qc_fix",
        "title": "Проверить QC",
        "domain": "qc",
        "priority": 2,
        "status": "open",
        "due_at": "2026-03-14T10:00:00+00:00",
        "owner_user_id": 7,
        "assignee_team": "team-qc",
        "sla_hours": 24,
        "sla_source": "cfg.default",
        "stage": "triage",
        "related_alert": "alert_1",
        "object_type": "animal",
        "object_id": "1001",
        "attachments": [{"kind": "csv", "path": "a.csv"}],
        "why": {"source": "qc"},
        "what_to_do": [{"step": "inspect"}],
        "data_version": "dv1",
        "qc_run": "qc1",
        "model_version": "m1",
        "scoring_run": "s1",
        "report_version": "r1",
        "dedupe_key": "dk1",
        "closed_reason": None,
        "closed_at": None,
        "assigned_at": None,
        "started_at": None,
        "is_overdue": False,
    }

    task = task_from_row(row)
    payload = task_to_api_dict(task)

    assert payload["task_id"] == "task_1"
    assert payload["priority"] == 2
    assert payload["attachments"] == [{"kind": "csv", "path": "a.csv"}]
    assert payload["why"] == {"source": "qc"}
    assert payload["what_to_do"] == [{"step": "inspect"}]
    assert payload["status"] == "open"
    assert payload["sla_source"] == "cfg.default"


def test_t15_03_decision_and_runmeta_serialization_stay_backward_compatible() -> None:
    decision = DecisionRecord(
        schema="genomeai.decision_record.v1",
        created_at_utc="2026-03-13T10:00:00+00:00",
        user="analyst",
        animal_id="1001",
        lactation_id="1001__3",
        recommendation_type="mastitis_followup",
        decision="accept",
        comment="ok",
        lactation_no=3,
        farm_id="farm_1",
        scoring_run="score_1",
    )
    meta = RunMeta(run_id="run_1", created_at_utc="2026-03-13T10:00:00+00:00", notes="baseline")

    assert decision_record_to_legacy_dict(decision) == {
        "schema": "genomeai.decision_record.v1",
        "created_at_utc": "2026-03-13T10:00:00+00:00",
        "user": "analyst",
        "animal_id": "1001",
        "lactation_id": "1001__3",
        "recommendation_type": "mastitis_followup",
        "decision": "accept",
        "comment": "ok",
        "lactation_no": 3,
        "farm_id": "farm_1",
        "scoring_run": "score_1",
    }
    assert run_meta_to_legacy_dict(meta) == {
        "run_id": "run_1",
        "created_at_utc": "2026-03-13T10:00:00+00:00",
        "tool": "genomeai",
        "schema": "genomeai.run_metadata.v1",
        "notes": "baseline",
    }


def test_t15_03_feedback_reason_codes_are_centralized_defaults() -> None:
    assert "CONFIRMED_BY_MANAGER" in DEFAULT_ACCEPTED_REASON_CODES
    assert "LOW_CONFIDENCE" in DEFAULT_REJECTED_REASON_CODES
    assert len(DEFAULT_ACCEPTED_REASON_CODES) == len(set(DEFAULT_ACCEPTED_REASON_CODES))
    assert len(DEFAULT_REJECTED_REASON_CODES) == len(set(DEFAULT_REJECTED_REASON_CODES))

def test_t15_03_target_models_use_centralized_enums_with_legacy_string_surface() -> None:
    event = Event(
        event_id="ev_1",
        animal_id="1001",
        event_date=date(2026, 3, 13),
        event_type="health_check",
        severity=EventSeverity.HIGH,
    )
    alert = Alert(
        alert_id="al_1",
        farm_id="farm_1",
        alert_date=date(2026, 3, 13),
        severity=AlertSeverity.CRITICAL,
        alert_type="qc_error",
        entity_type="animal",
        entity_id="1001",
        message="critical issue",
    )
    decision = Decision(
        decision_id="dec_1",
        farm_id="farm_1",
        decision_date=date(2026, 3, 13),
        animal_id="1001",
        recommendation_type="mastitis_followup",
        decision=RecommendationDecision.ACCEPT,
    )

    assert event.severity == EventSeverity.HIGH.value
    assert alert.severity == AlertSeverity.CRITICAL.value
    assert decision.decision == RecommendationDecision.ACCEPT.value


def test_t15_03_target_models_legacy_dump_preserves_string_and_iso_date_shape() -> None:
    alert = Alert(
        alert_id="al_2",
        farm_id="farm_1",
        alert_date=date(2026, 3, 14),
        severity="warn",
        alert_type="repro_delay",
        entity_type="lactation",
        entity_id="1001__3",
        message="follow up",
    )

    dumped = canonical_model_to_legacy_dict(alert)

    assert dumped == {
        "tenant_id": "default",
        "created_at": None,
        "updated_at": None,
        "alert_id": "al_2",
        "farm_id": "farm_1",
        "alert_date": "2026-03-14",
        "severity": "warn",
        "alert_type": "repro_delay",
        "entity_type": "lactation",
        "entity_id": "1001__3",
        "message": "follow up",
    }



def test_t15_03_shared_workflow_helpers_preserve_legacy_validation_messages() -> None:
    cfg = load_feedback_config(Path("configs/feedback/reason_codes.yaml"))
    assert reason_codes_for_feedback_decision("accepted", cfg) == tuple(cfg.accepted_codes)
    validate_feedback_decision_and_reason(decision="rejected", reason_code="LOW_CONFIDENCE", cfg=cfg)

    try:
        validate_feedback_decision_and_reason(decision="maybe", reason_code="LOW_CONFIDENCE", cfg=cfg)
    except ValueError as exc:
        assert str(exc) == "invalid_decision: expected accepted|rejected"
    else:  # pragma: no cover
        raise AssertionError("feedback decision validation drifted")

    assert normalize_task_active_status_for_update("open") == "open"
    assert normalize_task_close_status("done") == "done"

    try:
        normalize_task_active_status_for_update("done")
    except ValueError as exc:
        assert str(exc) == "invalid_status_for_update: allowed open|in_progress, got done"
    else:  # pragma: no cover
        raise AssertionError("task update status validation drifted")

    try:
        require_draft_approval_status("archived", entity_label="План", action_label="approval", forbidden_word="запрещен")
    except ValueError as exc:
        assert str(exc) == "План в статусе archived: approval запрещен"
    else:  # pragma: no cover
        raise AssertionError("approval guard drifted")
