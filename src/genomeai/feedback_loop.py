from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.domain import (
    DEFAULT_ACCEPTED_REASON_CODES,
    DEFAULT_REJECTED_REASON_CODES,
    FeedbackConfig,
    reason_codes_for_feedback_decision,
    task_outcome_label_from_status,
    validate_feedback_decision_and_reason,
)

DEFAULT_CFG_PATH = Path("configs/feedback/reason_codes.yaml")

def load_feedback_config(path: Path = DEFAULT_CFG_PATH) -> FeedbackConfig:
    try:
        import yaml  # type: ignore

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        raw = raw or {}
    except Exception:
        raw = {}

    metrics = raw.get("metrics") or {}
    reason_codes = raw.get("reason_codes") or {}
    dataset = raw.get("dataset") or {}
    accepted = tuple(str(x).strip() for x in list(reason_codes.get("accepted") or []) if str(x).strip())
    rejected = tuple(str(x).strip() for x in list(reason_codes.get("rejected") or []) if str(x).strip())
    try:
        wd = int(metrics.get("default_window_days") or 30)
    except Exception:
        wd = 30
    buckets_raw = list(metrics.get("latency_buckets_hours") or [])
    buckets: list[int] = []
    for item in buckets_raw:
        try:
            val = int(item)
        except Exception:
            continue
        if val > 0:
            buckets.append(val)
    try:
        default_sample_weight = float(dataset.get("default_sample_weight") or 1.0)
    except Exception:
        default_sample_weight = 1.0
    weight_items: list[tuple[str, float]] = []
    for key, value in dict(dataset.get("sample_weight_by_reason") or {}).items():
        code = str(key or "").strip()
        if not code:
            continue
        try:
            weight_items.append((code, float(value)))
        except Exception:
            continue
    return FeedbackConfig(
        default_window_days=max(1, wd),
        accepted_codes=accepted or DEFAULT_ACCEPTED_REASON_CODES,
        rejected_codes=rejected or DEFAULT_REJECTED_REASON_CODES,
        latency_buckets_hours=tuple(sorted(set(buckets))) or FeedbackConfig.latency_buckets_hours,
        default_sample_weight=float(default_sample_weight) if default_sample_weight > 0 else 1.0,
        sample_weight_by_reason=tuple(weight_items),
    )


def reason_codes_for_decision(decision: str, cfg: FeedbackConfig) -> tuple[str, ...]:
    return reason_codes_for_feedback_decision(decision, cfg)


def validate_feedback_payload(*, decision: str, reason_code: str, cfg: FeedbackConfig) -> None:
    validate_feedback_decision_and_reason(decision=decision, reason_code=reason_code, cfg=cfg)


def make_recommendation_id(
    *,
    recommendation_id: Optional[str],
    source: str,
    related_alert: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
) -> str:
    rid = str(recommendation_id or "").strip()
    if rid:
        return rid
    parts = ["rec", str(source or "manual").strip() or "manual"]
    for value in (scoring_run, report_version, related_alert):
        token = str(value or "").strip()
        if token:
            parts.append(token)
    ot = str(object_type or "").strip()
    oi = str(object_id or "").strip()
    if ot or oi:
        parts.append(f"{ot}:{oi}")
    return ":".join(parts)


def _task_outcome_label(status: Any) -> Any:
    return task_outcome_label_from_status(status)


def enrich_feedback_training_columns(df: pd.DataFrame, *, cfg: Optional[FeedbackConfig] = None) -> pd.DataFrame:
    cfg = cfg or FeedbackConfig()
    out = df.copy()
    decision = out.get("decision", pd.Series(dtype="object")).astype(str).str.lower().str.strip()
    out["feedback_target_label"] = decision.map({"accepted": 1, "rejected": 0}).astype("Int64")
    out["feedback_target_name"] = decision.where(decision.isin(["accepted", "rejected"]), "unknown")
    out["feedback_is_latest"] = True
    out["has_feedback_comment"] = out.get("comment", pd.Series(dtype="object")).fillna("").astype(str).str.strip().ne("")
    out["has_task_link"] = out.get("task_id", pd.Series(dtype="object")).fillna("").astype(str).str.strip().ne("")
    out["has_task_outcome"] = out.get("task_status", pd.Series(dtype="object")).fillna("").astype(str).str.strip().ne("")
    out["task_outcome_label"] = out.get("task_status", pd.Series(dtype="object")).apply(_task_outcome_label).astype("Int64")
    out["task_outcome_name"] = out.get("task_status", pd.Series(dtype="object")).fillna("").astype(str).replace({"": "unknown"})

    weights = {str(k): float(v) for k, v in cfg.sample_weight_by_reason}
    reason = out.get("reason_code", pd.Series(dtype="object")).fillna("").astype(str).str.strip()
    out["feedback_sample_weight"] = reason.map(weights).fillna(float(cfg.default_sample_weight)).astype(float).round(3)
    return out


def _recommendation_key_series(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="object")
    key = df.get("recommendation_id", pd.Series(index=df.index, dtype="object")).fillna("").astype(str).str.strip()
    fallback = df.get("feedback_id", pd.Series(index=df.index, dtype="object")).fillna("").astype(str).str.strip()
    return key.where(key != "", fallback)


def build_feedback_dataset(
    feedback_rows: list[dict[str, Any]],
    task_rows: Optional[list[dict[str, Any]]] = None,
    *,
    latest_only: bool = True,
    cfg: Optional[FeedbackConfig] = None,
) -> pd.DataFrame:
    df = pd.DataFrame(feedback_rows or [])
    if df.empty:
        return pd.DataFrame(
            columns=[
                "feedback_id",
                "recommendation_id",
                "decision",
                "reason_code",
                "comment",
                "created_at",
                "recommendation_created_at",
                "decision_seconds",
                "decision_hours",
                "related_alert",
                "task_id",
                "task_status",
                "task_closed_reason",
                "task_closed_at",
                "feedback_source",
                "object_type",
                "object_id",
                "farm_id",
                "group_id",
                "data_version",
                "model_version",
                "report_version",
                "qc_run",
                "scoring_run",
                "decision_id",
                "feedback_target_label",
                "feedback_target_name",
                "feedback_sample_weight",
                "task_outcome_label",
                "task_outcome_name",
                "has_task_link",
                "has_task_outcome",
                "has_feedback_comment",
                "feedback_is_latest",
            ]
        )

    for col in (
        "feedback_id", "recommendation_id", "decision", "reason_code", "comment", "related_alert", "task_id",
        "feedback_source", "object_type", "object_id", "farm_id", "group_id", "data_version", "model_version",
        "report_version", "qc_run", "scoring_run", "decision_id"
    ):
        if col not in df.columns:
            df[col] = ""

    df["created_at"] = pd.to_datetime(df.get("created_at"), errors="coerce", utc=True)
    df["recommendation_created_at"] = pd.to_datetime(df.get("recommendation_created_at"), errors="coerce", utc=True)
    if "decision_seconds" not in df.columns:
        df["decision_seconds"] = pd.NA
    if "metadata_json" in df.columns:
        def _meta_value(payload: Any, key: str) -> Any:
            try:
                obj = json.loads(str(payload or "{}"))
            except Exception:
                obj = {}
            return obj.get(key)
        if "feedback_source" not in df.columns or not df["feedback_source"].astype(str).str.len().any():
            df["feedback_source"] = df.get("metadata_json").apply(lambda x: _meta_value(x, "source"))
    mask = df["decision_seconds"].isna() & df["recommendation_created_at"].notna() & df["created_at"].notna()
    if mask.any():
        delta = (df.loc[mask, "created_at"] - df.loc[mask, "recommendation_created_at"]).dt.total_seconds().round()
        df.loc[mask, "decision_seconds"] = delta
    df["decision_seconds"] = pd.to_numeric(df["decision_seconds"], errors="coerce")
    df["decision_hours"] = (df["decision_seconds"] / 3600.0).round(3)

    if latest_only:
        df = df.sort_values(["recommendation_id", "created_at", "feedback_id"], kind="stable")
        key = _recommendation_key_series(df)
        df = df.assign(_latest_key=key).drop_duplicates(subset=["_latest_key"], keep="last").drop(columns=["_latest_key"])

    tdf = pd.DataFrame(task_rows or [])
    if not tdf.empty:
        for col in ("task_id", "related_alert", "object_type", "object_id", "status", "closed_reason", "closed_at", "updated_at"):
            if col not in tdf.columns:
                tdf[col] = ""
        tdf["_task_order"] = pd.to_datetime(tdf.get("closed_at"), errors="coerce", utc=True)
        fill = pd.to_datetime(tdf.get("updated_at"), errors="coerce", utc=True)
        tdf["_task_order"] = tdf["_task_order"].fillna(fill)
        tdf = tdf.sort_values(["_task_order", "task_id"], kind="stable")

        exact = tdf.drop_duplicates(subset=["task_id"], keep="last")[["task_id", "status", "closed_reason", "closed_at"]].rename(
            columns={"status": "task_status", "closed_reason": "task_closed_reason", "closed_at": "task_closed_at"}
        )
        df = df.merge(exact, how="left", on="task_id")

        unresolved = df["task_status"].isna()
        if unresolved.any() and "related_alert" in df.columns:
            by_alert = tdf[tdf["related_alert"].astype(str) != ""].drop_duplicates(subset=["related_alert"], keep="last")
            by_alert = by_alert[["related_alert", "task_id", "status", "closed_reason", "closed_at"]].rename(
                columns={"task_id": "task_id_alert", "status": "task_status_alert", "closed_reason": "task_closed_reason_alert", "closed_at": "task_closed_at_alert"}
            )
            df = df.merge(by_alert, how="left", on="related_alert")
            fill_cols = [
                ("task_id", "task_id_alert"),
                ("task_status", "task_status_alert"),
                ("task_closed_reason", "task_closed_reason_alert"),
                ("task_closed_at", "task_closed_at_alert"),
            ]
            for target, src in fill_cols:
                df[target] = df[target].where(df[target].notna() & (df[target].astype(str) != ""), df[src])
            df = df.drop(columns=[c for _, c in fill_cols if c in df.columns])

        unresolved = df["task_status"].isna()
        if unresolved.any() and {"object_type", "object_id"}.issubset(df.columns):
            by_obj = tdf[(tdf["object_type"].astype(str) != "") & (tdf["object_id"].astype(str) != "")]
            by_obj = by_obj.drop_duplicates(subset=["object_type", "object_id"], keep="last")
            by_obj = by_obj[["object_type", "object_id", "task_id", "status", "closed_reason", "closed_at"]].rename(
                columns={"task_id": "task_id_obj", "status": "task_status_obj", "closed_reason": "task_closed_reason_obj", "closed_at": "task_closed_at_obj"}
            )
            df = df.merge(by_obj, how="left", on=["object_type", "object_id"])
            fill_cols = [
                ("task_id", "task_id_obj"),
                ("task_status", "task_status_obj"),
                ("task_closed_reason", "task_closed_reason_obj"),
                ("task_closed_at", "task_closed_at_obj"),
            ]
            for target, src in fill_cols:
                df[target] = df[target].where(df[target].notna() & (df[target].astype(str) != ""), df[src])
            df = df.drop(columns=[c for _, c in fill_cols if c in df.columns])
    else:
        df["task_status"] = pd.NA
        df["task_closed_reason"] = pd.NA
        df["task_closed_at"] = pd.NA

    df = enrich_feedback_training_columns(df, cfg=cfg)

    ordered_cols = [
        "feedback_id",
        "recommendation_id",
        "decision",
        "reason_code",
        "comment",
        "created_at",
        "recommendation_created_at",
        "decision_seconds",
        "decision_hours",
        "related_alert",
        "task_id",
        "task_status",
        "task_closed_reason",
        "task_closed_at",
        "feedback_source",
        "object_type",
        "object_id",
        "farm_id",
        "group_id",
        "data_version",
        "model_version",
        "report_version",
        "qc_run",
        "scoring_run",
        "decision_id",
        "feedback_target_label",
        "feedback_target_name",
        "feedback_sample_weight",
        "task_outcome_label",
        "task_outcome_name",
        "has_task_link",
        "has_task_outcome",
        "has_feedback_comment",
        "feedback_is_latest",
    ]
    rest = [c for c in df.columns if c not in ordered_cols and c not in {"metadata_json"}]
    return df[ordered_cols + rest].copy()


def build_feedback_history_dataset(
    feedback_rows: list[dict[str, Any]],
    task_rows: Optional[list[dict[str, Any]]] = None,
    *,
    cfg: Optional[FeedbackConfig] = None,
) -> pd.DataFrame:
    history = build_feedback_dataset(feedback_rows, task_rows, latest_only=False, cfg=cfg)
    if history.empty:
        return pd.DataFrame(columns=list(history.columns) + [
            "feedback_sequence_no",
            "feedback_events_count",
            "previous_decision",
            "decision_changed_from_previous",
            "recommendation_first_decision",
            "recommendation_latest_decision",
            "recommendation_has_conflict",
        ])

    history = history.sort_values(["recommendation_id", "created_at", "feedback_id"], kind="stable").copy()
    rec_key = _recommendation_key_series(history)
    history["_rec_key"] = rec_key
    grp = history.groupby("_rec_key", dropna=False, sort=False)
    decision_norm = history.get("decision", pd.Series(index=history.index, dtype="object")).fillna("").astype(str).str.strip().str.lower()
    history["feedback_sequence_no"] = (grp.cumcount() + 1).astype("Int64")
    history["feedback_events_count"] = grp["feedback_id"].transform("size").astype("Int64")
    history["previous_decision"] = grp["decision"].shift(1)
    history["decision_changed_from_previous"] = (
        history["previous_decision"].fillna("").astype(str).str.strip().ne("")
        & history["previous_decision"].fillna("").astype(str).str.strip().str.lower().ne(decision_norm)
    )
    history["recommendation_first_decision"] = grp["decision"].transform("first")
    history["recommendation_latest_decision"] = grp["decision"].transform("last")
    conflict = grp["decision"].transform(
        lambda s: int(s.fillna("").astype(str).str.strip().str.lower().replace({"": pd.NA}).dropna().nunique() > 1)
    )
    history["recommendation_has_conflict"] = conflict.astype(bool)

    ordered_extra = [
        "feedback_sequence_no",
        "feedback_events_count",
        "previous_decision",
        "decision_changed_from_previous",
        "recommendation_first_decision",
        "recommendation_latest_decision",
        "recommendation_has_conflict",
    ]
    base_cols = [c for c in history.columns if c not in {"_rec_key"} and c not in ordered_extra]
    return history[base_cols + ordered_extra].copy()


def _rate(numerator: int, denominator: int) -> float:
    return round((float(numerator) / float(denominator)), 4) if denominator else 0.0


def _group_metrics(window: pd.DataFrame, col: str) -> list[dict[str, Any]]:
    if col not in window.columns:
        return []
    grp = window.assign(_group=window[col].fillna("").astype(str).str.strip())
    grp["_group"] = grp["_group"].replace({"": "unknown"})
    rows: list[dict[str, Any]] = []
    for key, sub in grp.groupby("_group", dropna=False):
        accepted = int((sub["decision"].astype(str).str.lower() == "accepted").sum())
        rejected = int((sub["decision"].astype(str).str.lower() == "rejected").sum())
        total = int(len(sub))
        rows.append({
            col: str(key),
            "feedback_total": total,
            "accepted_total": accepted,
            "rejected_total": rejected,
            "acceptance_rate": _rate(accepted, total),
        })
    rows.sort(key=lambda x: (-int(x.get("feedback_total") or 0), str(x.get(col) or "")))
    return rows


def _decision_time_buckets(window: pd.DataFrame, cfg: FeedbackConfig) -> list[dict[str, Any]]:
    secs = pd.to_numeric(window.get("decision_seconds"), errors="coerce")
    valid = secs.dropna()
    if valid.empty:
        return []
    hours = valid / 3600.0
    cutoffs = list(cfg.latency_buckets_hours)
    buckets: list[dict[str, Any]] = []
    prev = 0
    for bound in cutoffs:
        mask = (hours > prev) & (hours <= bound)
        label = f"<= {bound}h" if prev == 0 else f"> {prev}h .. <= {bound}h"
        buckets.append({"bucket": label, "count": int(mask.sum())})
        prev = bound
    buckets.append({"bucket": f"> {prev}h", "count": int((hours > prev).sum())})
    return [b for b in buckets if int(b.get("count") or 0) > 0]


def _task_outcomes_by_decision(window: pd.DataFrame) -> list[dict[str, Any]]:
    if "task_status" not in window.columns or "decision" not in window.columns:
        return []
    df = window.copy()
    df["decision"] = df["decision"].fillna("").astype(str).str.strip().str.lower().replace({"": "unknown"})
    df["task_status"] = df["task_status"].fillna("").astype(str).str.strip().replace({"": "unknown"})
    grp = (
        df.groupby(["decision", "task_status"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["count", "decision", "task_status"], ascending=[False, True, True], kind="stable")
    )
    return grp.to_dict(orient="records")


def _reason_acceptance_summary(window: pd.DataFrame) -> list[dict[str, Any]]:
    if "reason_code" not in window.columns or "decision" not in window.columns:
        return []
    df = window.copy()
    df["reason_code"] = df["reason_code"].fillna("").astype(str).str.strip().replace({"": "unknown"})
    df["decision"] = df["decision"].fillna("").astype(str).str.strip().str.lower().replace({"": "unknown"})
    rows: list[dict[str, Any]] = []
    for code, sub in df.groupby("reason_code", dropna=False):
        total = int(len(sub))
        accepted = int((sub["decision"] == "accepted").sum())
        rejected = int((sub["decision"] == "rejected").sum())
        rows.append({
            "reason_code": str(code),
            "feedback_total": total,
            "accepted_total": accepted,
            "rejected_total": rejected,
            "acceptance_rate": _rate(accepted, total),
        })
    rows.sort(key=lambda x: (-int(x.get("feedback_total") or 0), str(x.get("reason_code") or "")))
    return rows


def _recommendation_context_preview(window: pd.DataFrame, *, limit: int = 10) -> list[dict[str, Any]]:
    if window.empty:
        return []
    cols = [
        "recommendation_id",
        "decision",
        "reason_code",
        "feedback_source",
        "object_type",
        "object_id",
        "related_alert",
        "task_id",
        "task_status",
        "data_version",
        "model_version",
        "report_version",
        "scoring_run",
        "decision_hours",
        "created_at",
    ]
    keep = [c for c in cols if c in window.columns]
    if not keep:
        return []
    df = window.sort_values(["created_at", "recommendation_id"], ascending=[False, True], kind="stable").head(max(int(limit), 1))[keep].copy()
    return json.loads(df.fillna("").to_json(orient="records", force_ascii=False, date_format="iso"))


def _recommendation_history_preview(history_window: pd.DataFrame, *, limit: int = 10) -> list[dict[str, Any]]:
    if history_window.empty:
        return []
    hist = history_window.copy()
    rec_key = _recommendation_key_series(hist)
    hist["_rec_key"] = rec_key
    hist = hist.sort_values(["created_at", "feedback_id"], ascending=[False, False], kind="stable")
    latest = hist.drop_duplicates(subset=["_rec_key"], keep="first")
    focus = latest[(latest.get("feedback_events_count", 0).fillna(0).astype(int) > 1) | latest.get("recommendation_has_conflict", False).fillna(False).astype(bool)]
    if focus.empty:
        focus = latest[latest.get("feedback_events_count", 0).fillna(0).astype(int) > 1]
    if focus.empty:
        return []
    cols = [
        "recommendation_id",
        "feedback_events_count",
        "recommendation_first_decision",
        "recommendation_latest_decision",
        "recommendation_has_conflict",
        "decision_changed_from_previous",
        "reason_code",
        "feedback_source",
        "object_type",
        "object_id",
        "scoring_run",
        "report_version",
        "created_at",
    ]
    keep = [c for c in cols if c in focus.columns]
    return json.loads(focus.head(max(int(limit), 1))[keep].fillna("").to_json(orient="records", force_ascii=False, date_format="iso"))


def compute_feedback_metrics(
    feedback_rows: list[dict[str, Any]],
    task_rows: Optional[list[dict[str, Any]]] = None,
    *,
    window_days: Optional[int] = None,
    now_utc: Any = None,
    cfg: Optional[FeedbackConfig] = None,
) -> dict[str, Any]:
    cfg = cfg or FeedbackConfig()
    dataset = build_feedback_dataset(feedback_rows, task_rows, latest_only=True, cfg=cfg)
    history = build_feedback_history_dataset(feedback_rows, task_rows, cfg=cfg)
    if dataset.empty:
        return {
            "window_days": int(window_days or cfg.default_window_days),
            "feedback_total": 0,
            "feedback_events_total": 0,
            "accepted_total": 0,
            "rejected_total": 0,
            "acceptance_rate": 0.0,
            "median_time_to_decision_hours": None,
            "by_reason_code": [],
            "rejection_reasons": [],
            "reason_acceptance_summary": [],
            "by_feedback_source": [],
            "by_object_type": [],
            "by_scoring_run": [],
            "by_report_version": [],
            "by_model_version": [],
            "decision_time_buckets": [],
            "task_outcomes": {},
            "task_outcomes_by_decision": [],
            "task_linked_total": 0,
            "task_linked_rate": 0.0,
            "task_outcome_known_total": 0,
            "task_outcome_known_rate": 0.0,
            "multi_feedback_recommendations_total": 0,
            "multi_feedback_recommendations_rate": 0.0,
            "decision_changed_total": 0,
            "decision_changed_rate": 0.0,
            "recommendation_context_preview": [],
            "recommendation_history_preview": [],
            "top_accept_reason_code": None,
            "top_reject_reason_code": None,
        }

    now = pd.Timestamp.utcnow() if now_utc is None else pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    wd = int(window_days or cfg.default_window_days)
    cutoff = now - pd.Timedelta(days=wd)
    window = dataset[dataset["created_at"].notna() & (dataset["created_at"] >= cutoff)].copy()
    if window.empty:
        window = dataset.copy()
    history_window = history[history["created_at"].notna() & (history["created_at"] >= cutoff)].copy() if not history.empty else history.copy()
    if history_window.empty:
        history_window = history.copy()

    accepted_total = int((window["decision"].astype(str).str.lower() == "accepted").sum())
    rejected_total = int((window["decision"].astype(str).str.lower() == "rejected").sum())
    total = int(len(window))
    acc_rate = _rate(accepted_total, total)

    secs = pd.to_numeric(window.get("decision_seconds"), errors="coerce")
    median_hours = None
    if secs.notna().any():
        median_hours = round(float(secs.dropna().median()) / 3600.0, 3)

    by_reason = (
        window.assign(reason_code=window["reason_code"].astype(str))
        .groupby(["decision", "reason_code"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["count", "decision", "reason_code"], ascending=[False, True, True], kind="stable")
    )
    rejection = by_reason[by_reason["decision"].astype(str).str.lower() == "rejected"].copy()
    task_outcomes = {}
    if "task_status" in window.columns:
        ts = window["task_status"].astype(str)
        ts = ts[ts.str.strip() != ""]
        if not ts.empty:
            counts = ts.value_counts(dropna=False)
            task_outcomes = {str(k): int(v) for k, v in counts.items()}

    task_linked_total = int(window.get("has_task_link", pd.Series(dtype="bool")).fillna(False).astype(bool).sum())
    task_outcome_known_total = int(window.get("has_task_outcome", pd.Series(dtype="bool")).fillna(False).astype(bool).sum())

    history_feedback_events_total = int(len(history_window))
    history_latest = pd.DataFrame()
    if not history_window.empty:
        hist = history_window.copy()
        hist["_rec_key"] = _recommendation_key_series(hist)
        history_latest = hist.sort_values(["created_at", "feedback_id"], ascending=[False, False], kind="stable").drop_duplicates(subset=["_rec_key"], keep="first")
    multi_feedback_recommendations_total = int((history_latest.get("feedback_events_count", pd.Series(dtype="Int64")).fillna(0).astype(int) > 1).sum()) if not history_latest.empty else 0
    decision_changed_total = int(history_latest.get("recommendation_has_conflict", pd.Series(dtype="bool")).fillna(False).astype(bool).sum()) if not history_latest.empty else 0

    reason_rows = by_reason.to_dict(orient="records")
    rejection_rows = rejection.to_dict(orient="records")
    accept_rows = [r for r in reason_rows if str(r.get("decision") or "").lower() == "accepted"]

    return {
        "window_days": wd,
        "feedback_total": total,
        "feedback_events_total": history_feedback_events_total,
        "accepted_total": accepted_total,
        "rejected_total": rejected_total,
        "acceptance_rate": acc_rate,
        "median_time_to_decision_hours": median_hours,
        "by_reason_code": reason_rows,
        "rejection_reasons": rejection_rows,
        "reason_acceptance_summary": _reason_acceptance_summary(window),
        "by_feedback_source": _group_metrics(window, "feedback_source"),
        "by_object_type": _group_metrics(window, "object_type"),
        "by_scoring_run": _group_metrics(window, "scoring_run"),
        "by_report_version": _group_metrics(window, "report_version"),
        "by_model_version": _group_metrics(window, "model_version"),
        "decision_time_buckets": _decision_time_buckets(window, cfg),
        "task_outcomes": task_outcomes,
        "task_outcomes_by_decision": _task_outcomes_by_decision(window),
        "task_linked_total": task_linked_total,
        "task_linked_rate": _rate(task_linked_total, total),
        "task_outcome_known_total": task_outcome_known_total,
        "task_outcome_known_rate": _rate(task_outcome_known_total, total),
        "multi_feedback_recommendations_total": multi_feedback_recommendations_total,
        "multi_feedback_recommendations_rate": _rate(multi_feedback_recommendations_total, total),
        "decision_changed_total": decision_changed_total,
        "decision_changed_rate": _rate(decision_changed_total, total),
        "recommendation_context_preview": _recommendation_context_preview(window, limit=10),
        "recommendation_history_preview": _recommendation_history_preview(history_window, limit=10),
        "top_accept_reason_code": accept_rows[0].get("reason_code") if accept_rows else None,
        "top_reject_reason_code": rejection_rows[0].get("reason_code") if rejection_rows else None,
    }
