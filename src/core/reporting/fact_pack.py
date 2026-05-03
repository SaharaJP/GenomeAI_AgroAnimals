from __future__ import annotations

import json
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.application.ml_artifacts import (
    find_latest_model_version,
    find_latest_scoring_run,
    load_model_card,
    load_scoring_summary,
    load_train_summary,
    resolve_model_dir,
    resolve_scoring_dir,
)
from genomeai.alerts_v2 import generate_alerts_v2
from genomeai.playbooks import resolve_active_playbook


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _latest_dir(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return sorted(dirs, key=lambda p: p.name)[-1]


def _find_latest_kpi_run_root(artifacts_root: Path, data_version: str) -> Optional[Path]:
    runs_root = Path(artifacts_root) / data_version / "runs"
    if not runs_root.exists():
        return None
    candidates: List[Path] = []
    for run_dir in runs_root.iterdir():
        if run_dir.is_dir() and (run_dir / "kpi" / "kpi_summary.json").exists():
            candidates.append(run_dir)
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _load_latest_model_version(artifacts_root: Path, data_version: str) -> str:
    try:
        latest = find_latest_model_version(artifacts_root=artifacts_root, data_version=data_version)
        if latest:
            return str(latest)
    except Exception:
        pass
    return "NA"


def _resolve_output_path(
    raw_value: Any,
    *,
    artifacts_root: Path,
    default_dir: Path,
    fallbacks: Optional[List[Path]] = None,
) -> Path:
    candidates: List[Path] = []
    text = str(raw_value or "").strip()
    if text:
        raw_path = Path(text)
        candidates.append(raw_path if raw_path.is_absolute() else artifacts_root / raw_path)
        candidates.append(default_dir / raw_path)
    for fallback in fallbacks or []:
        candidates.append(Path(fallback))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved.exists():
            return resolved
    if candidates:
        return candidates[0]
    return default_dir


def _describe_numeric(series: pd.Series) -> Dict[str, Any]:
    s2 = pd.to_numeric(series, errors="coerce").dropna()
    if len(s2) == 0:
        return {"count": 0}
    q = s2.quantile([0.25, 0.5, 0.75]).to_dict()
    return {
        "count": int(len(s2)),
        "mean": float(s2.mean()),
        "std": float(s2.std(ddof=0)),
        "min": float(s2.min()),
        "p25": float(q.get(0.25, float("nan"))),
        "p50": float(q.get(0.5, float("nan"))),
        "p75": float(q.get(0.75, float("nan"))),
        "max": float(s2.max()),
    }


def _season_name_from_month(month: Optional[int]) -> str:
    if month is None:
        return "NA"
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "NA"


def _top_rows(df: pd.DataFrame, n: int = 20, cols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    out = df.head(n)
    if cols:
        keep = [c for c in cols if c in out.columns]
        if keep:
            out = out[keep]
    return json.loads(out.fillna("").to_json(orient="records", force_ascii=False))


def _build_mastitis_explainability_summary(rows: List[Dict[str, Any]], max_rows: int = 5) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "available": False,
        "top_feature_counts": {},
        "top_factors_preview": [],
        "counterfactuals_preview": [],
    }
    if not rows:
        return out
    counts: Dict[str, int] = {}
    top_preview: List[Dict[str, Any]] = []
    cf_preview: List[Dict[str, Any]] = []
    for row in rows[: max(int(max_rows), 1)]:
        animal_id = row.get("animal_id", "NA")
        tf = str(row.get("explain_top_factors_text") or "").strip()
        cf = str(row.get("explain_counterfactuals_text") or "").strip()
        if tf and tf != "insufficient_explainability_data":
            top_preview.append({"animal_id": animal_id, "top_factors_text": tf})
            feature = tf.split(";")[0].split("=")[0].strip()
            if feature:
                counts[feature] = counts.get(feature, 0) + 1
        if cf and cf != "no_simple_counterfactual":
            cf_preview.append({"animal_id": animal_id, "counterfactuals_text": cf})
    out["available"] = bool(top_preview or cf_preview)
    out["top_feature_counts"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5])
    out["top_factors_preview"] = top_preview[:max_rows]
    out["counterfactuals_preview"] = cf_preview[:max_rows]
    return out


def _build_mastitis_animal_explainability_rows(rows: List[Dict[str, Any]], max_rows: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows[: max(int(max_rows), 1)]:
        out.append(
            {
                "animal_id": row.get("animal_id", row.get("cow_id", "NA")),
                "farm_id": row.get("farm_id", "NA"),
                "risk_proba": row.get("risk_proba", row.get("risk_score", "NA")),
                "severity": row.get("severity", row.get("risk_flag", "NA")),
                "recommended_action": row.get("recommended_action", ""),
                "explain_top_factors_text": row.get("explain_top_factors_text", "insufficient_explainability_data"),
                "explain_counterfactuals_text": row.get("explain_counterfactuals_text", "no_simple_counterfactual"),
            }
        )
    return out


def _build_productivity_explainability_summary(rows: List[Dict[str, Any]], max_rows: int = 5) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "available": False,
        "top_feature_counts": {},
        "top_factors_preview": [],
        "counterfactuals_preview": [],
    }
    if not rows:
        return out
    counts: Dict[str, int] = {}
    tf_preview: List[Dict[str, Any]] = []
    cf_preview: List[Dict[str, Any]] = []
    for row in rows[: max(int(max_rows), 1)]:
        animal_id = row.get("animal_id", "NA")
        tf = str(row.get("explain_top_factors_text") or "").strip()
        cf = str(row.get("explain_counterfactuals_text") or "").strip()
        if tf and tf != "insufficient_explainability_data":
            tf_preview.append({"animal_id": animal_id, "top_factors_text": tf})
            feature = tf.split(";")[0].split("=")[0].strip()
            if feature:
                counts[feature] = counts.get(feature, 0) + 1
        if cf and cf != "no_simple_counterfactual":
            cf_preview.append({"animal_id": animal_id, "counterfactuals_text": cf})
    out["available"] = bool(tf_preview or cf_preview)
    out["top_feature_counts"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5])
    out["top_factors_preview"] = tf_preview[:max_rows]
    out["counterfactuals_preview"] = cf_preview[:max_rows]
    return out


def _build_productivity_animal_explainability_rows(rows: List[Dict[str, Any]], max_rows: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows[: max(int(max_rows), 1)]:
        out.append(
            {
                "animal_id": row.get("animal_id", "NA"),
                "farm_id": row.get("farm_id", "NA"),
                "prediction": row.get("y_pred", "NA"),
                "confidence": row.get("confidence", "NA"),
                "action": row.get("action", "NA"),
                "explain_top_factors_text": row.get("explain_top_factors_text", "insufficient_explainability_data"),
                "explain_counterfactuals_text": row.get("explain_counterfactuals_text", "no_simple_counterfactual"),
            }
        )
    return out


def build_assistant_fact_pack(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: str,
    scoring_run: str,
) -> Dict[str, Any]:
    artifacts_root = Path(artifacts_root)
    base = artifacts_root / data_version
    qc_dir = base / "qc" / qc_run
    model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    score_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)

    qc_summary = _read_json(qc_dir / "qc_summary.json")
    model_card = load_model_card(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    train_summary = load_train_summary(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version) or None
    scoring_summary = load_scoring_summary(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)

    rec_path = _resolve_output_path(
        (scoring_summary.get("outputs") or {}).get("recommendations_xlsx", ""),
        artifacts_root=artifacts_root,
        default_dir=score_dir,
        fallbacks=[score_dir / "exports" / "recommendations.xlsx"],
    )
    ranked_csv_path = _resolve_output_path(
        (scoring_summary.get("outputs") or {}).get("scored_latest_csv", ""),
        artifacts_root=artifacts_root,
        default_dir=score_dir,
        fallbacks=[score_dir / "scored_latest.csv"],
    )

    priority_df = observe_df = cull_df = pd.DataFrame()
    if rec_path.exists():
        try:
            priority_df = pd.read_excel(rec_path, sheet_name="priority")
            observe_df = pd.read_excel(rec_path, sheet_name="observe")
            cull_df = pd.read_excel(rec_path, sheet_name="cull_candidates")
        except Exception:
            priority_df = observe_df = cull_df = pd.DataFrame()

    scored_df = pd.DataFrame()
    if ranked_csv_path.exists():
        try:
            scored_df = pd.read_csv(ranked_csv_path)
        except Exception:
            scored_df = pd.DataFrame()

    dist: Dict[str, Any] = {}
    if len(scored_df) > 0:
        if "y_pred" in scored_df.columns:
            dist["y_pred"] = _describe_numeric(scored_df["y_pred"])
        if "residual" in scored_df.columns:
            dist["residual"] = _describe_numeric(scored_df["residual"])
        if "group_size" in scored_df.columns:
            dist["group_size"] = _describe_numeric(scored_df["group_size"])

    confidence_counts: Dict[str, int] = {}
    if len(scored_df) > 0 and "confidence" in scored_df.columns:
        confidence_counts = scored_df["confidence"].fillna("NA").astype(str).value_counts().to_dict()
        confidence_counts = {str(k): int(v) for k, v in confidence_counts.items()}

    temporal: Dict[str, Any] = {}
    if len(scored_df) > 0 and "calving_date" in scored_df.columns:
        calv = pd.to_datetime(scored_df["calving_date"], errors="coerce")
        temporal["calving_year_counts"] = calv.dt.year.dropna().astype(int).value_counts().sort_index().to_dict()
        seasonal = calv.dt.month.dropna().astype(int).map(_season_name_from_month)
        temporal["calving_season_counts"] = seasonal.value_counts().to_dict()

    fact_pack: Dict[str, Any] = {
        "schema": "genomeai.fact_pack.v1",
        "created_at_utc": _utc_now_iso(),
        "versions": {
            "data_version": data_version,
            "qc_run": qc_run,
            "model_version": model_version,
            "scoring_run": scoring_run,
        },
        "qc": {
            "qc_status": qc_summary.get("qc_status"),
            "datasets_loaded": qc_summary.get("datasets_loaded"),
            "metrics": qc_summary.get("metrics", {}),
            "qc_summary_path": str((qc_dir / "qc_summary.json").resolve()),
            "qc_report_xlsx": qc_summary.get("outputs", {}).get("qc_report_xlsx"),
        },
        "ml": {
            "task": model_card.get("task"),
            "target": model_card.get("target"),
            "features": model_card.get("features"),
            "split": model_card.get("split"),
            "metrics": model_card.get("metrics"),
            "limitations": model_card.get("limitations"),
            "model_card_path": str((model_dir / "model_card.json").resolve()),
            "train_summary": train_summary,
        },
        "scoring": {
            "status": scoring_summary.get("status"),
            "row_counts": scoring_summary.get("row_counts", {}),
            "inputs": scoring_summary.get("inputs", {}),
            "outputs": {
                **(scoring_summary.get("outputs", {}) or {}),
                "recommendations_xlsx": str(rec_path.resolve()) if rec_path.exists() else str(rec_path),
                "scored_latest_csv": str(ranked_csv_path.resolve()) if ranked_csv_path.exists() else str(ranked_csv_path),
            },
            "confidence_counts": confidence_counts,
        },
        "top_lists": {
            "priority": _top_rows(priority_df, n=20),
            "observe": _top_rows(observe_df, n=20),
            "cull_candidates": _top_rows(cull_df, n=20),
        },
        "distributions": dist,
        "temporal": temporal,
    }

    mastitis: Dict[str, Any] = {"available": False}
    try:
        mastitis_base = base / "mastitis" / "scoring"
        if mastitis_base.exists():
            runs = sorted([p for p in mastitis_base.iterdir() if p.is_dir()])
            if runs:
                mastitis_run = runs[-1]
                summary_path = mastitis_run / "scoring_summary.json"
                scores_path = mastitis_run / "mastitis_risk_scores.csv"
                expl_path = mastitis_run / "mastitis_explanations.csv"
                summary = _read_json(summary_path) if summary_path.exists() else {}
                scores = pd.read_csv(scores_path) if scores_path.exists() else pd.DataFrame()
                if not scores.empty:
                    top_risk_rows = _top_rows(scores, n=20)
                    mastitis = {
                        "available": True,
                        "scoring_run": mastitis_run.name,
                        "asof_date": summary.get("asof_date"),
                        "horizon_days": summary.get("horizon_days"),
                        "risk_threshold": summary.get("risk_threshold"),
                        "top_risk": top_risk_rows,
                        "animal_explainability": _build_mastitis_animal_explainability_rows(top_risk_rows),
                        "explainability": _build_mastitis_explainability_summary(top_risk_rows),
                        "paths": {
                            "scoring_summary_json": str(summary_path.resolve()),
                            "risk_scores_csv": str(scores_path.resolve()),
                            "explanations_csv": str(expl_path.resolve()) if expl_path.exists() else "NA",
                        },
                    }
    except Exception:
        mastitis = {"available": False}
    fact_pack["mastitis_risk"] = mastitis

    productivity_explainability: Dict[str, Any] = {"available": False}
    try:
        explain_rows: List[Dict[str, Any]] = []
        if len(scored_df) > 0 and "explain_top_factors_text" in scored_df.columns:
            explain_df = scored_df.copy()
            explain_df = explain_df[
                (explain_df["explain_top_factors_text"].fillna("").astype(str) != "insufficient_explainability_data")
                | (
                    explain_df.get("explain_counterfactuals_text", pd.Series([], dtype="object"))
                    .fillna("")
                    .astype(str)
                    != "no_simple_counterfactual"
                )
            ]
            if not explain_df.empty:
                sort_cols = [c for c in ["action", "y_pred"] if c in explain_df.columns]
                if sort_cols:
                    ascending = [True if c == "action" else False for c in sort_cols]
                    explain_df = explain_df.sort_values(sort_cols, ascending=ascending)
                explain_rows = _top_rows(explain_df, n=20)
        if explain_rows:
            productivity_explainability = {
                "available": True,
                "scoring_run": scoring_run,
                "animal_explainability": _build_productivity_animal_explainability_rows(explain_rows),
                "explainability": _build_productivity_explainability_summary(explain_rows),
                "paths": {
                    "scored_latest_csv": str(ranked_csv_path.resolve()) if ranked_csv_path.exists() else "NA",
                    "explanations_csv": scoring_summary.get("outputs", {}).get("explanations_csv", "NA"),
                },
            }
    except Exception:
        productivity_explainability = {"available": False}
    fact_pack["productivity_explainability"] = productivity_explainability

    farm_ctx = ""
    try:
        if mastitis.get("available") and (mastitis.get("top_risk") or []):
            farm_ctx = str((mastitis.get("top_risk") or [])[0].get("farm_id") or "").strip()
    except Exception:
        farm_ctx = ""
    if not farm_ctx:
        try:
            if len(scored_df) > 0 and "farm_id" in scored_df.columns:
                vals = scored_df["farm_id"].dropna().astype(str)
                farm_ctx = str(vals.head(1).tolist()[0] if not vals.empty else "").strip()
        except Exception:
            farm_ctx = ""

    recommended: List[Dict[str, Any]] = []
    if mastitis.get("available"):
        pb = resolve_active_playbook(target_kind="alert", target_type="ML.MASTITIS_RISK", farm_id=farm_ctx or None)
        if pb:
            recommended.append(pb)

    qc_status = str(fact_pack.get("qc", {}).get("qc_status") or "").upper()
    if qc_status and qc_status not in ("OK", "PASS", "DONE"):
        pb2 = resolve_active_playbook(target_kind="alert", target_type="QC.GENERIC", farm_id=farm_ctx or None)
        if pb2:
            recommended.append(pb2)
        pb3 = resolve_active_playbook(target_kind="task", target_type="data_correction", farm_id=farm_ctx or None)
        if pb3:
            recommended.append(pb3)

    uniq: Dict[str, Dict[str, Any]] = {}
    for item in recommended:
        key = f"{item.get('playbook_key','')}|{item.get('farm_id','')}|{item.get('version_id','')}"
        uniq[key] = item

    fact_pack["playbooks"] = {
        "available": bool(uniq),
        "farm_id_context": farm_ctx or "",
        "recommended": list(uniq.values()),
    }
    return fact_pack


def build_regular_fact_pack(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str,
    max_rows: int = 20,
) -> Dict[str, Any]:
    artifacts_root = Path(artifacts_root).resolve()
    dv = str(data_version)

    kpi_block: Dict[str, Any] = {"available": False}
    kpi_run_root = _find_latest_kpi_run_root(artifacts_root, dv)
    if kpi_run_root is not None:
        kpi_dir = kpi_run_root / "kpi"
        kpi_summary = _read_json(kpi_dir / "kpi_summary.json") if (kpi_dir / "kpi_summary.json").exists() else {}
        kpi_wide = _safe_read_csv(kpi_dir / "kpi_wide.csv")
        kpi_alerts = _safe_read_csv(kpi_dir / "kpi_alerts.csv")
        kpi_block = {
            "available": True,
            "run_id": kpi_summary.get("run_id", kpi_run_root.name),
            "asof_date": kpi_summary.get("asof_date", asof_date),
            "currency": kpi_summary.get("currency", "NA"),
            "kpi_count": kpi_summary.get("kpi_count", int(kpi_wide.shape[0]) if not kpi_wide.empty else 0),
            "alert_count": kpi_summary.get("alert_count", int(kpi_alerts.shape[0]) if not kpi_alerts.empty else 0),
            "kpi_wide_top": _top_rows(kpi_wide, n=max_rows),
            "kpi_alerts_top": _top_rows(kpi_alerts, n=max_rows),
            "sources": {
                "kpi_summary": str((kpi_dir / "kpi_summary.json").resolve()) if (kpi_dir / "kpi_summary.json").exists() else "NA",
                "kpi_wide": str((kpi_dir / "kpi_wide.csv").resolve()) if (kpi_dir / "kpi_wide.csv").exists() else "NA",
                "kpi_alerts": str((kpi_dir / "kpi_alerts.csv").resolve()) if (kpi_dir / "kpi_alerts.csv").exists() else "NA",
            },
        }

    repro_block: Dict[str, Any] = {"available": False}
    repro_root = artifacts_root / dv / "repro" / "runs"
    repro_run = _latest_dir(repro_root)
    if repro_run is not None:
        manifest = _read_json(repro_run / "run_manifest.json") if (repro_run / "run_manifest.json").exists() else {}
        kpis = _safe_read_csv(repro_run / "repro_kpis_farm.csv")
        worklists = _safe_read_csv(repro_run / "repro_worklists.csv")
        repro_block = {
            "available": True,
            "run_id": manifest.get("run_id", repro_run.name),
            "asof_date": (manifest.get("params", {}) or {}).get("asof_date", "NA"),
            "kpis_top": _top_rows(kpis, n=max_rows),
            "worklists_counts": (worklists["worklist_type"].value_counts().to_dict() if (not worklists.empty and "worklist_type" in worklists.columns) else {}),
            "worklists_top": _top_rows(worklists.sort_values(["priority"], ascending=[True]) if (not worklists.empty and "priority" in worklists.columns) else worklists, n=max_rows),
            "sources": {
                "run_manifest": str((repro_run / "run_manifest.json").resolve()) if (repro_run / "run_manifest.json").exists() else "NA",
                "kpis_csv": str((repro_run / "repro_kpis_farm.csv").resolve()) if (repro_run / "repro_kpis_farm.csv").exists() else "NA",
                "worklists_csv": str((repro_run / "repro_worklists.csv").resolve()) if (repro_run / "repro_worklists.csv").exists() else "NA",
                "xlsx": str((repro_run / "repro_kpi_worklists.xlsx").resolve()) if (repro_run / "repro_kpi_worklists.xlsx").exists() else "NA",
            },
        }

    mating_block: Dict[str, Any] = {"available": False}
    mating_root = artifacts_root / dv / "mating_plan"
    mating_run = _latest_dir(mating_root)
    if mating_run is not None:
        summary = _read_json(mating_run / "summary.json") if (mating_run / "summary.json").exists() else {}
        mating_df = _safe_read_csv(mating_run / "mating_plan.csv")
        mating_block = {
            "available": True,
            "run_id": summary.get("mating_plan_run", mating_run.name),
            "counts": summary.get("counts", {}),
            "top_pairs": _top_rows(mating_df, n=max_rows),
            "sources": {
                "summary_json": str((mating_run / "summary.json").resolve()) if (mating_run / "summary.json").exists() else "NA",
                "mating_plan_csv": str((mating_run / "mating_plan.csv").resolve()) if (mating_run / "mating_plan.csv").exists() else "NA",
                "mating_plan_xlsx": str((mating_run / "mating_plan.xlsx").resolve()) if (mating_run / "mating_plan.xlsx").exists() else "NA",
            },
        }

    economics_block: Dict[str, Any] = {"available": False}
    economics_root = artifacts_root / dv / "economics"
    economics_run = _latest_dir(economics_root)
    if economics_run is not None:
        summary_farm = _safe_read_csv(economics_run / "summary_farm.csv")
        params = {}
        if (economics_run / "whatif_params.json").exists():
            try:
                params = _read_json(economics_run / "whatif_params.json")
            except Exception:
                params = {}
        economics_block = {
            "available": True,
            "economics_run": economics_run.name,
            "params": params,
            "summary_farm_top": _top_rows(summary_farm, n=max_rows),
            "sources": {
                "summary_farm": str((economics_run / "summary_farm.csv").resolve()) if (economics_run / "summary_farm.csv").exists() else "NA",
                "xlsx": str((economics_run / "economics_whatif.xlsx").resolve()) if (economics_run / "economics_whatif.xlsx").exists() else "NA",
                "whatif_params": str((economics_run / "whatif_params.json").resolve()) if (economics_run / "whatif_params.json").exists() else "NA",
            },
        }

    mastitis: Dict[str, Any] = {"available": False}
    try:
        score_base = artifacts_root / dv / "mastitis" / "scoring"
        mastitis_run = _latest_dir(score_base)
        if mastitis_run is not None:
            summary = _read_json(mastitis_run / "scoring_summary.json") if (mastitis_run / "scoring_summary.json").exists() else {}
            scores = _safe_read_csv(mastitis_run / "mastitis_risk_scores.csv")
            expl_path = mastitis_run / "mastitis_explanations.csv"
            top_risk_rows = _top_rows(scores, n=max_rows)
            mastitis = {
                "available": True,
                "scoring_run": mastitis_run.name,
                "asof_date": summary.get("asof_date"),
                "horizon_days": summary.get("horizon_days"),
                "risk_threshold": summary.get("risk_threshold"),
                "top_risk": top_risk_rows,
                "animal_explainability": _build_mastitis_animal_explainability_rows(top_risk_rows, max_rows=max_rows),
                "explainability": _build_mastitis_explainability_summary(top_risk_rows, max_rows=max_rows),
                "sources": {
                    "scoring_summary_json": str((mastitis_run / "scoring_summary.json").resolve()) if (mastitis_run / "scoring_summary.json").exists() else "NA",
                    "risk_scores_csv": str((mastitis_run / "mastitis_risk_scores.csv").resolve()) if (mastitis_run / "mastitis_risk_scores.csv").exists() else "NA",
                    "explanations_csv": str(expl_path.resolve()) if expl_path.exists() else "NA",
                },
            }
    except Exception:
        mastitis = {"available": False}

    try:
        today = datetime.strptime(asof_date, "%Y-%m-%d").date()
    except Exception:
        today = _date.today()
    try:
        alerts = generate_alerts_v2(artifacts_root=artifacts_root, data_version=dv, today=today)
    except Exception:
        alerts = []

    pb_items: List[Dict[str, Any]] = []
    try:
        top_alerts = alerts[: min(len(alerts), 10)]
        uniq_types: List[str] = []
        for alert in top_alerts:
            alert_type = str(alert.get("alert_type") or "").strip()
            if alert_type and alert_type not in uniq_types:
                uniq_types.append(alert_type)
        for alert_type in uniq_types[:10]:
            playbook = resolve_active_playbook(target_kind="alert", target_type=alert_type, farm_id=None)
            if playbook:
                pb_items.append(playbook)
        if mastitis.get("available"):
            playbook = resolve_active_playbook(target_kind="alert", target_type="ML.MASTITIS_RISK", farm_id=None)
            if playbook:
                pb_items.append(playbook)
    except Exception:
        pb_items = []

    pb_uniq: Dict[str, Dict[str, Any]] = {}
    for playbook in pb_items:
        key = f"{playbook.get('playbook_key','')}|{playbook.get('farm_id','')}|{playbook.get('version_id','')}"
        pb_uniq[key] = playbook
    playbooks_block = {
        "available": bool(pb_uniq),
        "count": int(len(pb_uniq)),
        "recommended": list(pb_uniq.values()),
        "sources": {"note": "best-effort: from web.db active versions if available, else defaults.yaml"},
    }

    fact_pack: Dict[str, Any] = {
        "schema": "genomeai.fact_pack.regular.v1",
        "created_at_utc": _utc_now_iso(),
        "period": str(period),
        "asof_date": str(asof_date),
        "versions": {
            "data_version": dv,
            "model_version": _load_latest_model_version(artifacts_root, dv),
        },
        "modules": {
            "kpi": kpi_block,
            "alerts_v2": {
                "available": True,
                "count": int(len(alerts)),
                "top": alerts[:max_rows],
                "sources": {
                    "generator": "genomeai.alerts_v2.generate_alerts_v2",
                    "note": "deterministic rules from canonical+artifacts; no LLM",
                },
            },
            "playbooks": playbooks_block,
            "health": {"mastitis_risk": mastitis},
            "repro": repro_block,
            "mating": mating_block,
            "economics": economics_block,
        },
        "disclaimer": (
            "Decision-support: отчёт носит рекомендательный характер. "
            "Не является диагнозом или ветеринарным заключением. "
            "Все цифры и списки получены из витрин/алертов и указаны с источниками."
        ),
    }

    productivity = {"available": False}
    try:
        latest_model_version = str(fact_pack.get("versions", {}).get("model_version") or "NA")
        if latest_model_version != "NA":
            latest_scoring_run = find_latest_scoring_run(artifacts_root=artifacts_root, data_version=dv)
            latest_score_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=dv, scoring_run=latest_scoring_run) if latest_scoring_run else Path()
            scoring_summary = load_scoring_summary(artifacts_root=artifacts_root, data_version=dv, scoring_run=latest_scoring_run) if (latest_scoring_run and latest_score_dir.exists()) else {}
            scored_csv = _resolve_output_path(
                (scoring_summary.get("outputs") or {}).get("scored_latest_csv", ""),
                artifacts_root=artifacts_root,
                default_dir=latest_score_dir,
                fallbacks=[latest_score_dir / "scored_latest.csv"],
            )
            scored_df = pd.read_csv(scored_csv) if scored_csv.exists() else pd.DataFrame()
            explain_rows: List[Dict[str, Any]] = []
            if not scored_df.empty and "explain_top_factors_text" in scored_df.columns:
                explain_df = scored_df.copy()
                explain_df = explain_df[
                    (explain_df["explain_top_factors_text"].fillna("").astype(str) != "insufficient_explainability_data")
                    | (
                        explain_df.get("explain_counterfactuals_text", pd.Series([], dtype="object")).fillna("").astype(str)
                        != "no_simple_counterfactual"
                    )
                ]
                if not explain_df.empty:
                    sort_cols = [c for c in ["action", "y_pred"] if c in explain_df.columns]
                    if sort_cols:
                        ascending = [True if c == "action" else False for c in sort_cols]
                        explain_df = explain_df.sort_values(sort_cols, ascending=ascending)
                    explain_rows = _top_rows(explain_df, n=max_rows)
            if explain_rows:
                productivity = {
                    "available": True,
                    "scoring_run": str(latest_scoring_run),
                    "animal_explainability": _build_productivity_animal_explainability_rows(explain_rows, max_rows=max_rows),
                    "explainability": _build_productivity_explainability_summary(explain_rows, max_rows=max_rows),
                    "sources": {
                        "scored_latest_csv": str(scored_csv.resolve()) if scored_csv.exists() else "NA",
                        "scoring_summary_json": str((latest_score_dir / "scoring_summary.json").resolve()) if (latest_score_dir / "scoring_summary.json").exists() else "NA",
                    },
                }
    except Exception:
        productivity = {"available": False}
    fact_pack["modules"]["productivity_explainability"] = productivity
    return fact_pack


__all__ = [
    "build_assistant_fact_pack",
    "build_regular_fact_pack",
]
