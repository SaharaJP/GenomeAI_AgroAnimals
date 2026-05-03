from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from core.common.time import utc_isoformat_z, utc_timestamp_compact
from core.application.ml_artifacts import find_latest_scoring_run as _find_latest_scoring_run_v2, resolve_scoring_dir

from .decision_log import add_decision
from .versioning import ensure_run_dir, write_checksums, write_run_manifest


@dataclass
class ZootechDashboardInputs:
    data_version: str
    artifacts_dir: Path
    scoring_run: Optional[str] = None  # if omitted, auto-detect latest scoring run
    asof_date: Optional[date] = None


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _find_latest_scoring_run(artifacts_dir: Path, data_version: str) -> Optional[str]:
    return _find_latest_scoring_run_v2(artifacts_root=artifacts_dir, data_version=data_version)


def load_scoring_outputs(
    *,
    artifacts_dir: Path,
    data_version: str,
    scoring_run: Optional[str] = None,
) -> Tuple[str, pd.DataFrame, pd.DataFrame]:
    """Return (scoring_run, scored_latest_df, group_summary_df)."""
    sr = scoring_run or _find_latest_scoring_run(artifacts_dir, data_version)
    if not sr:
        raise FileNotFoundError(f"No scoring run found for data_version={data_version} in {artifacts_dir}")

    run_scoring_dir = resolve_scoring_dir(artifacts_root=artifacts_dir, data_version=data_version, scoring_run=sr)
    scored_latest = run_scoring_dir / "scored_latest.csv"
    group_summary = run_scoring_dir / "group_summary.csv"

    scored_df = _load_csv(scored_latest)
    group_df = _load_csv(group_summary)
    if scored_df.empty:
        raise FileNotFoundError(f"scored_latest.csv not found for scoring_run={sr}")

    return sr, scored_df, group_df


def compute_group_analytics(
    scored: pd.DataFrame,
    *,
    group_cols: Tuple[str, ...] = ("farm_id", "calving_year", "calving_season", "parity"),
) -> Dict[str, pd.DataFrame]:
    """Compute simple group analytics (distributions + outliers).

    This is intentionally lightweight: it must be fast, reproducible and based on scoring facts.
    """
    df = scored.copy()
    for c in ["y_pred", "residual", "milk_305d_kg"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Basic group stats
    gcols = [c for c in group_cols if c in df.columns]
    if not gcols:
        gcols = ["farm_id"] if "farm_id" in df.columns else []

    stats = (
        df.groupby(gcols, dropna=False)
        .agg(
            n_animals=("animal_id", "count") if "animal_id" in df.columns else (df.columns[0], "count"),
            mean_pred=("y_pred", "mean") if "y_pred" in df.columns else (df.columns[0], "count"),
            mean_residual=("residual", "mean") if "residual" in df.columns else (df.columns[0], "count"),
            p10_residual=("residual", lambda s: float(s.quantile(0.1))) if "residual" in df.columns else (df.columns[0], "count"),
            p90_residual=("residual", lambda s: float(s.quantile(0.9))) if "residual" in df.columns else (df.columns[0], "count"),
            share_low_conf=("confidence", lambda s: float((s == "LOW").mean())) if "confidence" in df.columns else (df.columns[0], "count"),
        )
        .reset_index()
    )

    # Outliers (simple, deterministic rules):
    # - residual <= -800 (low)
    # - residual >= +500 (high)
    out = pd.DataFrame()
    if "residual" in df.columns:
        out = df[(df["residual"] <= -800) | (df["residual"] >= 500)].copy()
        out["outlier_reason"] = out["residual"].apply(lambda r: "LOW" if pd.notna(r) and float(r) <= -800 else "HIGH")

    # Decision-support views
    priority = df[df.get("action") == "PRIORITY"].copy() if "action" in df.columns else pd.DataFrame()
    observe = df[df.get("action") == "OBSERVE"].copy() if "action" in df.columns else pd.DataFrame()
    cull = df[df.get("action") == "CULL_CANDIDATE"].copy() if "action" in df.columns else pd.DataFrame()

    return {
        "group_stats": stats,
        "outliers": out,
        "priority": priority,
        "observe": observe,
        "cull": cull,
    }


def export_zootech_dashboard(
    *,
    inputs: ZootechDashboardInputs,
    run_id: Optional[str] = None,
    user: str = "unknown",
) -> Path:
    """Export zootech dashboard snapshot to artifacts/<dv>/runs/<run_id>/dashboards/zootech_productivity/"""

    dv = inputs.data_version
    artifacts_dir = inputs.artifacts_dir
    asof = inputs.asof_date or date.today()

    sr, scored, group_summary = load_scoring_outputs(
        artifacts_dir=artifacts_dir,
        data_version=dv,
        scoring_run=inputs.scoring_run,
    )

    dash_run = run_id or f"dash_{utc_timestamp_compact()}"
    run_root = ensure_run_dir(artifacts_dir, dv, dash_run)
    out_dir = run_root / "dashboards" / "zootech_productivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    analytics = compute_group_analytics(scored)
    xlsx_path = out_dir / "zootech_productivity.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        scored.to_excel(xw, index=False, sheet_name="ranking")
        (group_summary if not group_summary.empty else analytics["group_stats"]).to_excel(xw, index=False, sheet_name="groups")
        analytics["outliers"].to_excel(xw, index=False, sheet_name="outliers")
        analytics["priority"].to_excel(xw, index=False, sheet_name="priority")
        analytics["observe"].to_excel(xw, index=False, sheet_name="observe")
        analytics["cull"].to_excel(xw, index=False, sheet_name="cull")

    # Create a simple decision template as a convenience (does not write decisions yet)
    decision_template = out_dir / "decision_candidates.xlsx"
    candidates_cols = [c for c in ["farm_id", "animal_id", "lactation_no", "calving_date", "y_pred", "residual", "confidence", "action", "action_reasons"] if c in scored.columns]
    cand = scored[candidates_cols].copy() if candidates_cols else scored.copy()
    with pd.ExcelWriter(decision_template, engine="openpyxl") as xw:
        cand[cand.get("action") == "PRIORITY"].to_excel(xw, index=False, sheet_name="priority")
        cand[cand.get("action") == "OBSERVE"].to_excel(xw, index=False, sheet_name="observe")
        cand[cand.get("action") == "CULL_CANDIDATE"].to_excel(xw, index=False, sheet_name="cull")

    summary = {
        "schema": "genomeai.dashboard.zootech_productivity.v1",
        "data_version": dv,
        "run_id": dash_run,
        "created_at": utc_isoformat_z(),
        "asof_date": asof.isoformat(),
        "inputs": {"scoring_run": sr},
        "outputs": {
            "zootech_xlsx": str(xlsx_path.relative_to(run_root)),
            "decision_candidates_xlsx": str(decision_template.relative_to(run_root)),
        },
        "lineage": {"scoring_run": sr},
        "notes": "Zootech snapshot is built strictly from scoring artifacts (no extra calculations in UI).",
    }
    (out_dir / "dashboard_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "1.0",
        "data_version": dv,
        "run_id": dash_run,
        "step": "dashboard.zootech_productivity",
        "created_at": summary["created_at"],
        "inputs": {"scoring_run": sr},
        "outputs": {
            "zootech_xlsx": str(xlsx_path.relative_to(run_root)),
            "decision_candidates_xlsx": str(decision_template.relative_to(run_root)),
            "dashboard_summary_json": str((out_dir / "dashboard_summary.json").relative_to(run_root)),
        },
        "lineage": {"scoring_run": sr},
    }

    write_checksums(run_root=run_root)
    write_run_manifest(run_root=run_root, manifest=manifest)
    write_checksums(run_root=run_root)
    return run_root


def write_decisions_from_dataframe(
    *,
    artifacts_dir: Path,
    data_version: str,
    scoring_run: str,
    user: str,
    df: pd.DataFrame,
    recommendation_type_col: str = "action",
    decision_col: str = "decision",
    comment_col: str = "comment",
) -> Tuple[int, str]:
    """Append decisions from a user-edited dataframe.

    Expected columns: animal_id, lactation_no (optional), farm_id (optional), action/action_reasons.
    lactation_id is synthesized from animal_id + lactation_no when missing.
    """
    if df.empty:
        return 0, "EMPTY"

    n_ok = 0
    for _, r in df.iterrows():
        animal_id = str(r.get("animal_id", ""))
        if not animal_id:
            continue
        lact_no = r.get("lactation_no")
        lact_id = f"{animal_id}__{int(lact_no)}" if pd.notna(lact_no) else f"{animal_id}__NA"
        rec_type = str(r.get(recommendation_type_col, ""))
        decision = str(r.get(decision_col, ""))
        comment = str(r.get(comment_col, ""))
        if not decision:
            continue

        ok, _msg = add_decision(
            artifacts_root=artifacts_dir,
            data_version=data_version,
            animal_id=animal_id,
            lactation_id=lact_id,
            recommendation_type=rec_type,
            decision=decision,
            comment=comment,
            user=user,
            lactation_no=int(lact_no) if pd.notna(lact_no) else None,
            farm_id=str(r.get("farm_id")) if pd.notna(r.get("farm_id")) else None,
            scoring_run=scoring_run,
        )
        if ok:
            n_ok += 1

    return n_ok, "OK"
