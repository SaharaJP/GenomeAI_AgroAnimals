from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.infra import ArtifactsRepo, CompletionOutcomesRepo, FeedbackRepo, TasksRepo

from genomeai.feedback_loop import (
    DEFAULT_CFG_PATH,
    load_feedback_config,
    make_recommendation_id,
    validate_feedback_payload,
)
from core.feedback_calibration_v2 import (
    build_feedback_dataset_v2,
    build_feedback_history_dataset_v2,
    build_recalibration_readiness_dataset_v2,
    compute_feedback_metrics_v2 as core_compute_feedback_metrics,
)

from core.infra.web_db import get_settings, utcnow_iso
from .decision_log_v2 import DecisionCreate, append_decision
from .entities import normalize_object_type


@dataclass
class FeedbackCreate:
    recommendation_id: Optional[str]
    decision: str
    reason_code: str
    comment: Optional[str]
    related_alert: Optional[str]
    task_id: Optional[str]
    object_type: Optional[str]
    object_id: Optional[str]
    farm_id: Optional[str]
    group_id: Optional[str]
    data_version: Optional[str]
    model_version: Optional[str]
    report_version: Optional[str]
    qc_run: Optional[str]
    scoring_run: Optional[str]
    recommendation_created_at: Optional[str]
    feedback_source: Optional[str]
    metadata: dict[str, Any]


def _cfg_path() -> Path:
    return get_settings().project_root / DEFAULT_CFG_PATH


def load_feedback_cfg() -> dict[str, Any]:
    cfg = load_feedback_config(_cfg_path())
    return {
        "metrics": {"default_window_days": cfg.default_window_days},
        "reason_codes": {
            "accepted": list(cfg.accepted_codes),
            "rejected": list(cfg.rejected_codes),
        },
    }


def record_feedback(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    fc: FeedbackCreate,
    user_id: int,
    username: str,
    created_at: Optional[str] = None,
    decision_reason: Optional[str] = None,
) -> dict[str, Any]:
    cfg = load_feedback_config(_cfg_path())
    validate_feedback_payload(decision=fc.decision, reason_code=fc.reason_code, cfg=cfg)

    decision = str(fc.decision or "").strip().lower()
    ts = created_at or utcnow_iso()
    recommendation_id = make_recommendation_id(
        recommendation_id=fc.recommendation_id,
        source=str(fc.feedback_source or "feedback_ui"),
        related_alert=fc.related_alert,
        object_type=fc.object_type,
        object_id=fc.object_id,
        scoring_run=fc.scoring_run,
        report_version=fc.report_version,
    )
    object_type = normalize_object_type(fc.object_type) or str(fc.object_type or "") or None
    feedback_id = uuid.uuid4().hex

    decision_id = append_decision(
        conn,
        tenant_id=tenant_id,
        d=DecisionCreate(
            recommendation_id=recommendation_id,
            action=f"recommendation.{decision}",
            user_id=int(user_id),
            username=str(username),
            reason=str(decision_reason or fc.reason_code),
            comment=(str(fc.comment) if fc.comment else None),
            related_alert=(str(fc.related_alert) if fc.related_alert else None),
            object_type=object_type,
            object_id=(str(fc.object_id) if fc.object_id else None),
            farm_id=(str(fc.farm_id) if fc.farm_id else None),
            group_id=(str(fc.group_id) if fc.group_id else None),
            data_version=(str(fc.data_version) if fc.data_version else None),
            model_version=(str(fc.model_version) if fc.model_version else None),
            report_version=(str(fc.report_version) if fc.report_version else None),
            qc_run=(str(fc.qc_run) if fc.qc_run else None),
            scoring_run=(str(fc.scoring_run) if fc.scoring_run else None),
            metadata={
                **(fc.metadata or {}),
                "feedback": {
                    "decision": decision,
                    "reason_code": fc.reason_code,
                    "source": fc.feedback_source,
                    "task_id": fc.task_id,
                },
            },
        ),
        created_at=ts,
    )

    recommendation_created_at = str(fc.recommendation_created_at or "").strip() or None
    decision_seconds = None
    if recommendation_created_at:
        try:
            delta = (pd.Timestamp(ts) - pd.Timestamp(recommendation_created_at)).total_seconds()
            if pd.notna(delta):
                decision_seconds = int(max(0, round(float(delta))))
        except Exception:
            decision_seconds = None

    FeedbackRepo(conn).insert_event(
        tenant_id=tenant_id,
        feedback_id=feedback_id,
        created_at=ts,
        recommendation_id=recommendation_id,
        decision=decision,
        reason_code=str(fc.reason_code),
        comment=(str(fc.comment) if fc.comment else None),
        recommendation_created_at=recommendation_created_at,
        decision_seconds=decision_seconds,
        related_alert=(str(fc.related_alert) if fc.related_alert else None),
        task_id=(str(fc.task_id) if fc.task_id else None),
        object_type=object_type,
        object_id=(str(fc.object_id) if fc.object_id else None),
        farm_id=(str(fc.farm_id) if fc.farm_id else None),
        group_id=(str(fc.group_id) if fc.group_id else None),
        data_version=(str(fc.data_version) if fc.data_version else None),
        model_version=(str(fc.model_version) if fc.model_version else None),
        report_version=(str(fc.report_version) if fc.report_version else None),
        qc_run=(str(fc.qc_run) if fc.qc_run else None),
        scoring_run=(str(fc.scoring_run) if fc.scoring_run else None),
        feedback_source=(str(fc.feedback_source) if fc.feedback_source else None),
        decision_id=decision_id,
        metadata=fc.metadata or {},
    )
    return {
        "feedback_id": feedback_id,
        "decision_id": decision_id,
        "recommendation_id": recommendation_id,
        "decision": decision,
        "reason_code": str(fc.reason_code),
    }


def list_feedback(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    recommendation_id: Optional[str] = None,
    decision: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return FeedbackRepo(conn).list_events(
        tenant_id=tenant_id,
        filters={
            "recommendation_id": str(recommendation_id) if recommendation_id else None,
            "decision": str(decision).strip().lower() if decision else None,
            "object_type": normalize_object_type(object_type) or str(object_type) if object_type else None,
            "object_id": str(object_id) if object_id else None,
            "data_version": str(data_version) if data_version else None,
            "scoring_run": str(scoring_run) if scoring_run else None,
            "report_version": str(report_version) if report_version else None,
            "feedback_source": str(feedback_source) if feedback_source else None,
            "model_version": str(model_version) if model_version else None,
        },
        limit=limit,
        offset=offset,
    )


def _load_task_rows(conn: sqlite3.Connection, tenant_id: str) -> list[dict[str, Any]]:
    return TasksRepo(conn).list_feedback_rows(tenant_id=tenant_id)


def _load_outcome_rows(
    conn: sqlite3.Connection,
    tenant_id: str,
) -> list[dict[str, Any]]:
    return CompletionOutcomesRepo(conn).list_feedback_rows(tenant_id=tenant_id)


def _load_feedback_rows(
    conn: sqlite3.Connection,
    tenant_id: str,
    *,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
) -> list[dict[str, Any]]:
    return FeedbackRepo(conn).list_rows(
        tenant_id=tenant_id,
        filters={
            "data_version": str(data_version) if data_version else None,
            "scoring_run": str(scoring_run) if scoring_run else None,
            "report_version": str(report_version) if report_version else None,
            "feedback_source": str(feedback_source) if feedback_source else None,
            "model_version": str(model_version) if model_version else None,
        },
    )


def compute_feedback_metrics(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    window_days: Optional[int] = None,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
) -> dict[str, Any]:
    cfg = load_feedback_config(_cfg_path())
    feedback_rows = _load_feedback_rows(
        conn,
        tenant_id,
        data_version=data_version,
        scoring_run=scoring_run,
        report_version=report_version,
        feedback_source=feedback_source,
        model_version=model_version,
    )
    task_rows = _load_task_rows(conn, tenant_id)
    outcome_rows = _load_outcome_rows(conn, tenant_id)
    metrics = core_compute_feedback_metrics(feedback_rows, task_rows, outcome_rows, window_days=window_days, cfg=cfg)
    preview = build_feedback_dataset_v2(feedback_rows, task_rows, outcome_rows, latest_only=True, cfg=cfg)
    history = build_feedback_history_dataset_v2(feedback_rows, task_rows, outcome_rows, cfg=cfg)
    recalibration = build_recalibration_readiness_dataset_v2(preview)
    preview_rows = json.loads(preview.head(20).to_json(orient="records", force_ascii=False, date_format="iso")) if not preview.empty else []
    history_rows = json.loads(history.head(20).to_json(orient="records", force_ascii=False, date_format="iso")) if not history.empty else []
    recalibration_rows = json.loads(recalibration.head(20).to_json(orient="records", force_ascii=False, date_format="iso")) if not recalibration.empty else []
    return {
        "metrics": metrics,
        "preview": preview_rows,
        "history_preview": history_rows,
        "recalibration_preview": recalibration_rows,
    }


def export_feedback_dataset(
    conn: sqlite3.Connection,
    *,
    artifacts_root: Path,
    tenant_id: str,
    feedback_run: str,
    data_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    feedback_source: Optional[str] = None,
    model_version: Optional[str] = None,
) -> dict[str, Any]:
    cfg = load_feedback_config(_cfg_path())
    feedback_rows = _load_feedback_rows(
        conn,
        tenant_id,
        data_version=data_version,
        scoring_run=scoring_run,
        report_version=report_version,
        feedback_source=feedback_source,
        model_version=model_version,
    )
    task_rows = _load_task_rows(conn, tenant_id)
    outcome_rows = _load_outcome_rows(conn, tenant_id)
    dataset = build_feedback_dataset_v2(feedback_rows, task_rows, outcome_rows, latest_only=True, cfg=cfg)
    history = build_feedback_history_dataset_v2(feedback_rows, task_rows, outcome_rows, cfg=cfg)
    recalibration = build_recalibration_readiness_dataset_v2(dataset)
    metrics = core_compute_feedback_metrics(feedback_rows, task_rows, outcome_rows, cfg=cfg)
    repo = ArtifactsRepo(get_settings().project_root, artifacts_root, get_settings().storage_dir)
    base = repo.ensure_dir(Path(artifacts_root) / "system" / "feedback" / str(feedback_run))
    csv_path = base / "feedback_dataset.csv"
    history_csv_path = base / "feedback_history.csv"
    recalibration_csv_path = base / "feedback_recalibration_readiness.csv"
    json_path = base / "manifest.json"
    metrics_path = base / "metrics_summary.json"
    repo.write_dataframe_csv(csv_path, dataset)
    repo.write_dataframe_csv(history_csv_path, history)
    repo.write_dataframe_csv(recalibration_csv_path, recalibration)
    repo.write_json(metrics_path, metrics)
    manifest = {
        "feedback_run": str(feedback_run),
        "tenant_id": str(tenant_id),
        "data_version_filter": str(data_version) if data_version else None,
        "scoring_run_filter": str(scoring_run) if scoring_run else None,
        "report_version_filter": str(report_version) if report_version else None,
        "feedback_source_filter": str(feedback_source) if feedback_source else None,
        "model_version_filter": str(model_version) if model_version else None,
        "rows": int(len(dataset)),
        "history_rows": int(len(history)),
        "recalibration_rows": int(len(recalibration)),
        "outputs": {
            "feedback_dataset_csv": str(csv_path.resolve()),
            "feedback_history_csv": str(history_csv_path.resolve()),
            "feedback_recalibration_readiness_csv": str(recalibration_csv_path.resolve()),
            "metrics_summary_json": str(metrics_path.resolve()),
        },
        "dataset_columns": list(dataset.columns),
        "history_dataset_columns": list(history.columns),
        "recalibration_dataset_columns": list(recalibration.columns),
        "metrics": metrics,
    }
    repo.write_json(json_path, manifest)
    return {
        "feedback_run": str(feedback_run),
        "rows": int(len(dataset)),
        "outputs": {
            "feedback_dataset_csv": str(csv_path.resolve()),
            "feedback_history_csv": str(history_csv_path.resolve()),
            "feedback_recalibration_readiness_csv": str(recalibration_csv_path.resolve()),
            "metrics_summary_json": str(metrics_path.resolve()),
            "manifest_json": str(json_path.resolve()),
        },
        "metrics": metrics,
        "dataset_columns": list(dataset.columns),
        "history_dataset_columns": list(history.columns),
        "recalibration_dataset_columns": list(recalibration.columns),
        "history_rows": int(len(history)),
        "recalibration_rows": int(len(recalibration)),
    }
