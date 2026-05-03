from __future__ import annotations

import json
from typing import Any, Optional

import pandas as pd

from genomeai.feedback_loop import (
    FeedbackConfig,
    build_feedback_dataset as build_feedback_dataset_base,
    build_feedback_history_dataset as build_feedback_history_dataset_base,
    compute_feedback_metrics as compute_feedback_metrics_base,
)

_OUTCOME_FINALS = {"done", "cancelled", "deferred", "no_effect", "escalated"}


def _decode_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return json.loads(str(value or "{}"))
    except Exception:
        return {}


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _to_text(value).lower()
    return text in {"1", "true", "yes", "y", "да"}



def _attach_raw_feedback_metadata(df: pd.DataFrame, feedback_rows: list[dict[str, Any]]) -> pd.DataFrame:
    out = df.copy()
    raw = pd.DataFrame(feedback_rows or [])
    if out.empty or raw.empty or 'feedback_id' not in out.columns or 'feedback_id' not in raw.columns:
        return out
    keep_cols = ['feedback_id']
    if 'metadata_json' in raw.columns:
        keep_cols.append('metadata_json')
    if 'metadata' in raw.columns:
        keep_cols.append('metadata')
    if len(keep_cols) == 1:
        return out
    raw_meta = raw[keep_cols].drop_duplicates(subset=['feedback_id'], keep='last')
    return out.merge(raw_meta, how='left', on='feedback_id')

def _metadata_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    meta_series = out.get("metadata", out.get("metadata_json", pd.Series(index=out.index, dtype="object"))).apply(_decode_metadata)
    out["feedback_metadata"] = meta_series

    def capture_at(row_meta: dict[str, Any]) -> dict[str, Any]:
        return dict(row_meta.get("capture_v2") or {})

    def assistant_ctx(row_meta: dict[str, Any]) -> dict[str, Any]:
        return dict(row_meta.get("assistant_context") or row_meta.get("assistant") or {})

    out["capture_v2"] = out["feedback_metadata"].apply(capture_at)
    out["assistant_context"] = out["feedback_metadata"].apply(assistant_ctx)

    out["feedback_context_kind"] = out["capture_v2"].apply(lambda x: _to_text(x.get("context_kind"))).replace({"": pd.NA})
    out["feedback_context_kind"] = out["feedback_context_kind"].fillna(
        out["assistant_context"].apply(lambda x: _to_text(x.get("context_kind")))
    )
    out["feedback_context_kind"] = out["feedback_context_kind"].fillna("")

    inferred_kind = out.get("feedback_source", pd.Series(index=out.index, dtype="object")).fillna("").astype(str).str.strip().str.lower().map(
        lambda s: "assistant_answer" if s.startswith("assistant") else "operational_decision"
    )
    out["feedback_kind"] = out["capture_v2"].apply(lambda x: _to_text(x.get("feedback_kind"))).replace({"": pd.NA}).fillna(inferred_kind).fillna("")

    out["override_applied"] = out["capture_v2"].apply(lambda x: _to_bool(x.get("override_applied") or x.get("override")))
    out["override_target"] = out["capture_v2"].apply(lambda x: _to_text(x.get("override_target")))
    out["override_comment"] = out["capture_v2"].apply(lambda x: _to_text(x.get("override_comment")))
    out["capture_outcome_status"] = out["capture_v2"].apply(lambda x: _to_text(x.get("outcome_status")))
    out["capture_outcome_reason_code"] = out["capture_v2"].apply(lambda x: _to_text(x.get("outcome_reason_code") or x.get("outcome_reason")))
    out["capture_action_observed_at"] = pd.to_datetime(
        out["capture_v2"].apply(lambda x: _to_text(x.get("action_observed_at"))), errors="coerce", utc=True
    )
    out["capture_linked_action"] = out["capture_v2"].apply(lambda x: _to_text(x.get("linked_action")))
    return out


def _merge_outcome_rows(df: pd.DataFrame, outcome_rows: Optional[list[dict[str, Any]]]) -> pd.DataFrame:
    out = df.copy()
    odf = pd.DataFrame(outcome_rows or [])
    for base in [
        "outcome_status_resolved",
        "outcome_reason_code_resolved",
        "outcome_created_at_resolved",
        "outcome_source_resolved",
        "linked_decision_id_resolved",
        "outcome_role_resolved",
    ]:
        out[base] = out.get(base, pd.Series(index=out.index, dtype="object"))
    if odf.empty:
        return out

    for col in ("task_id", "related_alert", "object_type", "object_id", "outcome_status", "reason_code", "created_at", "linked_decision_id", "outcome_role"):
        if col not in odf.columns:
            odf[col] = ""
    odf["created_at"] = pd.to_datetime(odf.get("created_at"), errors="coerce", utc=True)
    odf = odf.sort_values(["created_at"], ascending=[False], kind="stable")

    exact = odf[odf["task_id"].fillna("").astype(str).str.strip() != ""].drop_duplicates(subset=["task_id"], keep="first")
    if not exact.empty:
        exact = exact[["task_id", "outcome_status", "reason_code", "created_at", "linked_decision_id", "outcome_role"]].rename(columns={
            "outcome_status": "outcome_status_task",
            "reason_code": "outcome_reason_code_task",
            "created_at": "outcome_created_at_task",
            "linked_decision_id": "linked_decision_id_task",
            "outcome_role": "outcome_role_task",
        })
        out = out.merge(exact, how="left", on="task_id")
    else:
        for col in ["outcome_status_task", "outcome_reason_code_task", "outcome_created_at_task", "linked_decision_id_task", "outcome_role_task"]:
            out[col] = pd.NA

    unresolved = out["outcome_status_task"].isna() | (out["outcome_status_task"].astype(str).str.strip() == "")
    by_alert = odf[odf["related_alert"].fillna("").astype(str).str.strip() != ""].drop_duplicates(subset=["related_alert"], keep="first")
    if unresolved.any() and not by_alert.empty and "related_alert" in out.columns:
        by_alert = by_alert[["related_alert", "outcome_status", "reason_code", "created_at", "linked_decision_id", "outcome_role"]].rename(columns={
            "outcome_status": "outcome_status_alert",
            "reason_code": "outcome_reason_code_alert",
            "created_at": "outcome_created_at_alert",
            "linked_decision_id": "linked_decision_id_alert",
            "outcome_role": "outcome_role_alert",
        })
        out = out.merge(by_alert, how="left", on="related_alert")
    else:
        for col in ["outcome_status_alert", "outcome_reason_code_alert", "outcome_created_at_alert", "linked_decision_id_alert", "outcome_role_alert"]:
            out[col] = pd.NA

    unresolved = (
        out[["outcome_status_task", "outcome_status_alert"]].fillna("").astype(str).eq("").all(axis=1)
        if {"outcome_status_task", "outcome_status_alert"}.issubset(out.columns)
        else pd.Series(False, index=out.index)
    )
    by_obj = odf[(odf["object_type"].fillna("").astype(str).str.strip() != "") & (odf["object_id"].fillna("").astype(str).str.strip() != "")].drop_duplicates(subset=["object_type", "object_id"], keep="first")
    if unresolved.any() and not by_obj.empty and {"object_type", "object_id"}.issubset(out.columns):
        by_obj = by_obj[["object_type", "object_id", "outcome_status", "reason_code", "created_at", "linked_decision_id", "outcome_role"]].rename(columns={
            "outcome_status": "outcome_status_obj",
            "reason_code": "outcome_reason_code_obj",
            "created_at": "outcome_created_at_obj",
            "linked_decision_id": "linked_decision_id_obj",
            "outcome_role": "outcome_role_obj",
        })
        out = out.merge(by_obj, how="left", on=["object_type", "object_id"])
    else:
        for col in ["outcome_status_obj", "outcome_reason_code_obj", "outcome_created_at_obj", "linked_decision_id_obj", "outcome_role_obj"]:
            out[col] = pd.NA

    status_cols = [c for c in ["outcome_status_task", "outcome_status_alert", "outcome_status_obj"] if c in out.columns]
    reason_cols = [c for c in ["outcome_reason_code_task", "outcome_reason_code_alert", "outcome_reason_code_obj"] if c in out.columns]
    created_cols = [c for c in ["outcome_created_at_task", "outcome_created_at_alert", "outcome_created_at_obj"] if c in out.columns]
    linked_cols = [c for c in ["linked_decision_id_task", "linked_decision_id_alert", "linked_decision_id_obj"] if c in out.columns]
    role_cols = [c for c in ["outcome_role_task", "outcome_role_alert", "outcome_role_obj"] if c in out.columns]

    if status_cols:
        out["outcome_status_resolved"] = out[status_cols].bfill(axis=1).iloc[:, 0]
    if reason_cols:
        out["outcome_reason_code_resolved"] = out[reason_cols].bfill(axis=1).iloc[:, 0]
    if created_cols:
        out["outcome_created_at_resolved"] = out[created_cols].bfill(axis=1).iloc[:, 0]
    if linked_cols:
        out["linked_decision_id_resolved"] = out[linked_cols].bfill(axis=1).iloc[:, 0]
    if role_cols:
        out["outcome_role_resolved"] = out[role_cols].bfill(axis=1).iloc[:, 0]
    out["outcome_source_resolved"] = out["outcome_status_resolved"].apply(lambda v: "completion_outcomes" if _to_text(v) else "")
    return out


def _derive_action_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["task_closed_at"] = pd.to_datetime(out.get("task_closed_at"), errors="coerce", utc=True)
    out["recommendation_created_at"] = pd.to_datetime(out.get("recommendation_created_at"), errors="coerce", utc=True)
    out["outcome_created_at_resolved"] = pd.to_datetime(out.get("outcome_created_at_resolved"), errors="coerce", utc=True)

    out["outcome_status"] = out.get("outcome_status_resolved", pd.Series(index=out.index, dtype="object")).fillna("")
    blank_mask = out["outcome_status"].astype(str).str.strip().eq("")
    out.loc[blank_mask, "outcome_status"] = out.get("capture_outcome_status", pd.Series(index=out.index, dtype="object"))[blank_mask].fillna("")
    blank_mask = out["outcome_status"].astype(str).str.strip().eq("")
    if "task_status" in out.columns:
        task_status = out.get("task_status", pd.Series(index=out.index, dtype="object")).fillna("").astype(str).str.strip()
        out.loc[blank_mask, "outcome_status"] = task_status.where(task_status.isin(_OUTCOME_FINALS), "")[blank_mask]

    out["outcome_reason_code"] = out.get("outcome_reason_code_resolved", pd.Series(index=out.index, dtype="object")).fillna("")
    blank_mask = out["outcome_reason_code"].astype(str).str.strip().eq("")
    out.loc[blank_mask, "outcome_reason_code"] = out.get("capture_outcome_reason_code", pd.Series(index=out.index, dtype="object"))[blank_mask].fillna("")
    blank_mask = out["outcome_reason_code"].astype(str).str.strip().eq("")
    if "task_closed_reason" in out.columns:
        out.loc[blank_mask, "outcome_reason_code"] = out.get("task_closed_reason", pd.Series(index=out.index, dtype="object"))[blank_mask].fillna("")

    out["action_observed_at"] = out.get("outcome_created_at_resolved", pd.Series(index=out.index, dtype="datetime64[ns, UTC]"))
    blank_mask = pd.isna(out["action_observed_at"])
    out.loc[blank_mask, "action_observed_at"] = out.get("capture_action_observed_at", pd.Series(index=out.index, dtype="datetime64[ns, UTC]"))[blank_mask]
    blank_mask = pd.isna(out["action_observed_at"])
    out.loc[blank_mask, "action_observed_at"] = out.get("task_closed_at", pd.Series(index=out.index, dtype="datetime64[ns, UTC]"))[blank_mask]

    delta = (out["action_observed_at"] - out["recommendation_created_at"]).dt.total_seconds()
    delta = delta.where(delta.notna() & (delta >= 0))
    out["time_to_action_seconds"] = pd.to_numeric(delta, errors="coerce")
    out["time_to_action_hours"] = (out["time_to_action_seconds"] / 3600.0).round(3)
    out["outcome_known"] = out["outcome_status"].fillna("").astype(str).str.strip().ne("")
    return out


def _derive_recalibration_readiness(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    issues: list[list[str]] = []
    levels: list[str] = []
    flags: list[bool] = []
    with_outcome_flags: list[bool] = []
    for _, row in out.iterrows():
        row_issues: list[str] = []
        if not _to_text(row.get("object_type")):
            row_issues.append("missing_object_type")
        if not _to_text(row.get("object_id")):
            row_issues.append("missing_object_id")
        if not _to_text(row.get("data_version")):
            row_issues.append("missing_data_version")
        if not (_to_text(row.get("model_version")) or _to_text(row.get("scoring_run")) or _to_text(row.get("report_version"))):
            row_issues.append("missing_linked_versions")
        if not _to_text(row.get("feedback_source")):
            row_issues.append("missing_feedback_source")
        if pd.isna(row.get("created_at")):
            row_issues.append("missing_feedback_timestamp")
        if not _to_text(row.get("decision")):
            row_issues.append("missing_decision")
        if not _to_text(row.get("reason_code")):
            row_issues.append("missing_reason_code")

        basic_ready = not row_issues
        outcome_known = bool(row.get("outcome_known"))
        if basic_ready and outcome_known:
            level = "high"
        elif basic_ready:
            level = "medium"
        elif len(row_issues) <= 2 and _to_text(row.get("object_id")):
            level = "low"
        else:
            level = "not_ready"
        issues.append(row_issues)
        levels.append(level)
        flags.append(level in {"medium", "high"})
        with_outcome_flags.append(level == "high")

    out["recalibration_readiness_issues"] = [";".join(x) for x in issues]
    out["recalibration_ready_flag"] = flags
    out["recalibration_ready_with_outcome_flag"] = with_outcome_flags
    out["recalibration_readiness_level"] = levels
    return out


def build_feedback_dataset_v2(
    feedback_rows: list[dict[str, Any]],
    task_rows: Optional[list[dict[str, Any]]] = None,
    outcome_rows: Optional[list[dict[str, Any]]] = None,
    *,
    latest_only: bool = True,
    cfg: Optional[FeedbackConfig] = None,
) -> pd.DataFrame:
    ds = build_feedback_dataset_base(feedback_rows, task_rows, latest_only=latest_only, cfg=cfg)
    if ds.empty:
        for col in [
            "feedback_context_kind", "feedback_kind", "override_applied", "override_target", "override_comment",
            "capture_outcome_status", "capture_outcome_reason_code", "capture_linked_action", "outcome_status",
            "outcome_reason_code", "outcome_known", "time_to_action_seconds", "time_to_action_hours",
            "recalibration_ready_flag", "recalibration_ready_with_outcome_flag", "recalibration_readiness_level",
            "recalibration_readiness_issues",
        ]:
            ds[col] = pd.Series(dtype="object")
        return ds
    ds = _attach_raw_feedback_metadata(ds, feedback_rows)
    ds = _metadata_columns(ds)
    ds = _merge_outcome_rows(ds, outcome_rows)
    ds = _derive_action_metrics(ds)
    ds = _derive_recalibration_readiness(ds)
    return ds


def build_feedback_history_dataset_v2(
    feedback_rows: list[dict[str, Any]],
    task_rows: Optional[list[dict[str, Any]]] = None,
    outcome_rows: Optional[list[dict[str, Any]]] = None,
    *,
    cfg: Optional[FeedbackConfig] = None,
) -> pd.DataFrame:
    hist = build_feedback_history_dataset_base(feedback_rows, task_rows, cfg=cfg)
    if hist.empty:
        return build_feedback_dataset_v2([], task_rows=task_rows, outcome_rows=outcome_rows, latest_only=False, cfg=cfg)
    hist = _attach_raw_feedback_metadata(hist, feedback_rows)
    hist = _metadata_columns(hist)
    hist = _merge_outcome_rows(hist, outcome_rows)
    hist = _derive_action_metrics(hist)
    hist = _derive_recalibration_readiness(hist)
    return hist


def build_recalibration_readiness_dataset_v2(dataset_v2: pd.DataFrame) -> pd.DataFrame:
    if dataset_v2.empty:
        return pd.DataFrame(columns=[
            "recommendation_id", "decision", "reason_code", "feedback_source", "feedback_context_kind", "feedback_kind",
            "object_type", "object_id", "data_version", "model_version", "scoring_run", "report_version",
            "override_applied", "override_target", "outcome_status", "outcome_reason_code",
            "decision_hours", "time_to_action_hours", "recalibration_readiness_level", "recalibration_readiness_issues",
        ])
    cols = [
        "recommendation_id", "decision", "reason_code", "feedback_source", "feedback_context_kind", "feedback_kind",
        "object_type", "object_id", "data_version", "model_version", "scoring_run", "report_version",
        "override_applied", "override_target", "outcome_status", "outcome_reason_code",
        "decision_hours", "time_to_action_hours", "recalibration_ready_flag", "recalibration_ready_with_outcome_flag",
        "recalibration_readiness_level", "recalibration_readiness_issues",
    ]
    keep = [c for c in cols if c in dataset_v2.columns]
    out = dataset_v2[dataset_v2.get("recalibration_ready_flag", pd.Series(dtype="bool")).fillna(False).astype(bool)].copy()
    if out.empty:
        return pd.DataFrame(columns=keep)
    return out[keep].copy()


def _safe_rate(num: int, den: int) -> float:
    return round(float(num) / float(den), 4) if den else 0.0


def _group_counts(df: pd.DataFrame, col: str) -> list[dict[str, Any]]:
    if col not in df.columns:
        return []
    grp = df.assign(_g=df[col].fillna("").astype(str).str.strip().replace({"": "unknown"}))
    rows: list[dict[str, Any]] = []
    for key, sub in grp.groupby("_g", dropna=False):
        total = int(len(sub))
        accepted = int((sub.get("decision", pd.Series(index=sub.index, dtype="object")).astype(str).str.lower() == "accepted").sum())
        rows.append({col: str(key), "feedback_total": total, "accepted_total": accepted, "acceptance_rate": _safe_rate(accepted, total)})
    rows.sort(key=lambda x: (-int(x.get("feedback_total") or 0), str(x.get(col) or "")))
    return rows


def _quality_gaps_breakdown(df: pd.DataFrame) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for raw in df.get("recalibration_readiness_issues", pd.Series(dtype="object")).fillna("").astype(str):
        for token in [t.strip() for t in raw.split(";") if t.strip()]:
            counts[token] = counts.get(token, 0) + 1
    rows = [{"quality_gap": k, "count": int(v)} for k, v in counts.items()]
    rows.sort(key=lambda x: (-int(x.get("count") or 0), str(x.get("quality_gap") or "")))
    return rows


def compute_feedback_metrics_v2(
    feedback_rows: list[dict[str, Any]],
    task_rows: Optional[list[dict[str, Any]]] = None,
    outcome_rows: Optional[list[dict[str, Any]]] = None,
    *,
    window_days: Optional[int] = None,
    now_utc: Any = None,
    cfg: Optional[FeedbackConfig] = None,
) -> dict[str, Any]:
    cfg = cfg or FeedbackConfig()
    base = compute_feedback_metrics_base(feedback_rows, task_rows, window_days=window_days, now_utc=now_utc, cfg=cfg)
    ds = build_feedback_dataset_v2(feedback_rows, task_rows, outcome_rows, latest_only=True, cfg=cfg)
    hist = build_feedback_history_dataset_v2(feedback_rows, task_rows, outcome_rows, cfg=cfg)
    if ds.empty:
        return {
            **base,
            "assistant_feedback_total": 0,
            "operational_feedback_total": 0,
            "override_total": 0,
            "override_rate": 0.0,
            "outcome_linked_total": 0,
            "outcome_linked_rate": 0.0,
            "median_time_to_action_hours": None,
            "recalibration_ready_total": 0,
            "recalibration_ready_rate": 0.0,
            "recalibration_ready_with_outcome_total": 0,
            "recalibration_ready_with_outcome_rate": 0.0,
            "by_feedback_kind": [],
            "by_context_kind": [],
            "by_outcome_status": [],
            "by_override_flag": [],
            "quality_gaps_breakdown": [],
        }

    now = pd.Timestamp.utcnow() if now_utc is None else pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    wd = int(window_days or cfg.default_window_days)
    cutoff = now - pd.Timedelta(days=wd)
    window = ds[ds["created_at"].notna() & (ds["created_at"] >= cutoff)].copy() if "created_at" in ds.columns else ds.copy()
    if window.empty:
        window = ds.copy()
    hist_window = hist[hist["created_at"].notna() & (hist["created_at"] >= cutoff)].copy() if "created_at" in hist.columns else hist.copy()
    if hist_window.empty:
        hist_window = hist.copy()

    total = int(len(window))
    assistant_total = int((window.get("feedback_kind", pd.Series(index=window.index, dtype="object")).astype(str) == "assistant_answer").sum())
    operational_total = int((window.get("feedback_kind", pd.Series(index=window.index, dtype="object")).astype(str) != "assistant_answer").sum())
    override_total = int(window.get("override_applied", pd.Series(index=window.index, dtype="bool")).fillna(False).astype(bool).sum())
    outcome_linked_total = int(window.get("outcome_known", pd.Series(index=window.index, dtype="bool")).fillna(False).astype(bool).sum())
    ready_total = int(window.get("recalibration_ready_flag", pd.Series(index=window.index, dtype="bool")).fillna(False).astype(bool).sum())
    ready_outcome_total = int(window.get("recalibration_ready_with_outcome_flag", pd.Series(index=window.index, dtype="bool")).fillna(False).astype(bool).sum())
    tta = pd.to_numeric(window.get("time_to_action_hours"), errors="coerce")
    median_tta = round(float(tta.dropna().median()), 3) if tta.notna().any() else None

    outcome_status_rows = _group_counts(window.rename(columns={"outcome_status": "_outcome_status"}), "_outcome_status")
    for row in outcome_status_rows:
        row["outcome_status"] = row.pop("_outcome_status")
    override_rows = _group_counts(window.assign(_override_flag=window.get("override_applied", pd.Series(index=window.index, dtype="bool")).fillna(False).map({True: "override", False: "standard"})), "_override_flag")
    for row in override_rows:
        row["override_mode"] = row.pop("_override_flag")

    return {
        **base,
        "assistant_feedback_total": assistant_total,
        "operational_feedback_total": operational_total,
        "override_total": override_total,
        "override_rate": _safe_rate(override_total, total),
        "outcome_linked_total": outcome_linked_total,
        "outcome_linked_rate": _safe_rate(outcome_linked_total, total),
        "median_time_to_action_hours": median_tta,
        "recalibration_ready_total": ready_total,
        "recalibration_ready_rate": _safe_rate(ready_total, total),
        "recalibration_ready_with_outcome_total": ready_outcome_total,
        "recalibration_ready_with_outcome_rate": _safe_rate(ready_outcome_total, total),
        "by_feedback_kind": _group_counts(window, "feedback_kind"),
        "by_context_kind": _group_counts(window, "feedback_context_kind"),
        "by_outcome_status": outcome_status_rows,
        "by_override_flag": override_rows,
        "quality_gaps_breakdown": _quality_gaps_breakdown(window),
        "v2_recommendation_context_preview": json.loads(
            window[[c for c in [
                "recommendation_id", "decision", "reason_code", "feedback_kind", "feedback_context_kind", "override_applied",
                "outcome_status", "time_to_action_hours", "recalibration_readiness_level", "object_type", "object_id", "scoring_run", "report_version"
            ] if c in window.columns]].head(10).fillna("").to_json(orient="records", force_ascii=False, date_format="iso")
        ) if not window.empty else [],
        "v2_recommendation_history_preview": json.loads(
            hist_window[[c for c in [
                "recommendation_id", "feedback_events_count", "feedback_kind", "feedback_context_kind", "override_applied",
                "recommendation_has_conflict", "outcome_status", "recalibration_readiness_level", "reason_code", "created_at"
            ] if c in hist_window.columns]].head(10).fillna("").to_json(orient="records", force_ascii=False, date_format="iso")
        ) if not hist_window.empty else [],
    }


__all__ = [
    "build_feedback_dataset_v2",
    "build_feedback_history_dataset_v2",
    "build_recalibration_readiness_dataset_v2",
    "compute_feedback_metrics_v2",
]
