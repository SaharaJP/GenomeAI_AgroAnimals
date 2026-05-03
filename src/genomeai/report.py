from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.application.ml_artifacts import (
    load_model_card,
    load_scoring_summary,
    load_train_summary,
    resolve_model_dir,
    resolve_scoring_dir,
)

from core.reporting.assistant_reporting import (
    generate_assistant_report_text_fallback as _core_generate_assistant_report_text_fallback,
    generate_assistant_report_text_llm as _core_generate_assistant_report_text_llm,
    render_assistant_report_docx as _core_render_assistant_report_docx,
    render_assistant_report_pdf as _core_render_assistant_report_pdf,
)
from core.reporting.fact_pack import build_assistant_fact_pack
from core.reporting.entrypoints import run_assistant_report as _core_run_assistant_report
def run_assistant_report_use_case(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: str,
    scoring_run: str,
    mode: str = "fallback",
    report_version: Optional[str] = None,
    make_pdf: bool = True,
    llm_model: Optional[str] = None,
    **_ignored: Any,
) -> Dict[str, Any]:
    """Compatibility adapter preserving old use-case injection surface."""
    return _core_run_assistant_report(
        artifacts_root=artifacts_root,
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode=mode,
        report_version=report_version,
        make_pdf=make_pdf,
        llm_model=llm_model,
    )


from .versioning import compute_data_version, generate_run_id, write_json, get_run_root, write_run_manifest, write_checksums, copy_tree_into_run
from .playbooks import resolve_active_playbook


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _describe_numeric(s: pd.Series) -> Dict[str, Any]:
    s2 = pd.to_numeric(s, errors="coerce").dropna()
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


def _season_name_from_month(m: Optional[int]) -> str:
    if m is None:
        return "NA"
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    if m in (9, 10, 11):
        return "autumn"
    return "NA"


def _top_rows(df: pd.DataFrame, n: int = 20, cols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if df is None or len(df) == 0:
        return []
    out = df.head(n)
    if cols:
        keep = [c for c in cols if c in out.columns]
        out = out[keep]
    # json-friendly
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
            first_chunk = tf.split(";")[0]
            feature = first_chunk.split("=")[0].strip()
            if feature:
                counts[feature] = counts.get(feature, 0) + 1
        if cf and cf != "no_simple_counterfactual":
            cf_preview.append({"animal_id": animal_id, "counterfactuals_text": cf})
    out["available"] = bool(top_preview or cf_preview)
    out["top_feature_counts"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5])
    out["top_factors_preview"] = top_preview[:max_rows]
    out["counterfactuals_preview"] = cf_preview[:max_rows]
    return out


@dataclass
class ReportSummary:
    schema: str
    created_at_utc: str
    data_version: str
    qc_run: str
    model_version: str
    scoring_run: str
    report_version: str
    mode_requested: str
    llm_used: bool
    inputs: Dict[str, Any]
    outputs: Dict[str, str]




def _build_mastitis_animal_explainability_rows(rows: List[Dict[str, Any]], max_rows: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows[: max(int(max_rows), 1)]:
        out.append({
            "animal_id": row.get("animal_id", row.get("cow_id", "NA")),
            "farm_id": row.get("farm_id", "NA"),
            "risk_proba": row.get("risk_proba", row.get("risk_score", "NA")),
            "severity": row.get("severity", row.get("risk_flag", "NA")),
            "recommended_action": row.get("recommended_action", ""),
            "explain_top_factors_text": row.get("explain_top_factors_text", "insufficient_explainability_data"),
            "explain_counterfactuals_text": row.get("explain_counterfactuals_text", "no_simple_counterfactual"),
        })
    return out


def _build_productivity_explainability_summary(rows: List[Dict[str, Any]], max_rows: int = 5) -> Dict[str, Any]:
    out: Dict[str, Any] = {"available": False, "top_feature_counts": {}, "top_factors_preview": [], "counterfactuals_preview": []}
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
            feature = tf.split(';')[0].split('=')[0].strip()
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
        out.append({
            "animal_id": row.get("animal_id", "NA"),
            "farm_id": row.get("farm_id", "NA"),
            "prediction": row.get("y_pred", "NA"),
            "confidence": row.get("confidence", "NA"),
            "action": row.get("action", "NA"),
            "explain_top_factors_text": row.get("explain_top_factors_text", "insufficient_explainability_data"),
            "explain_counterfactuals_text": row.get("explain_counterfactuals_text", "no_simple_counterfactual"),
        })
    return out

def build_fact_pack(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: str,
    scoring_run: str,
) -> Dict[str, Any]:
    """Build a single JSON 'fact pack' used as the only source of truth for report generation."""
    base = artifacts_root / data_version
    qc_dir = base / "qc" / qc_run
    model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    score_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)

    qc_summary = _read_json(qc_dir / "qc_summary.json")
    model_card = load_model_card(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    train_summary = load_train_summary(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version) or None
    scoring_summary = load_scoring_summary(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)

    # Load scoring exports for top lists
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
            # keep empty; report will still build
            priority_df = observe_df = cull_df = pd.DataFrame()

    scored_df = pd.DataFrame()
    if ranked_csv_path.exists():
        try:
            scored_df = pd.read_csv(ranked_csv_path)
        except Exception:
            scored_df = pd.DataFrame()

    # Distributions
    dist: Dict[str, Any] = {}
    if len(scored_df) > 0:
        if "y_pred" in scored_df.columns:
            dist["y_pred"] = _describe_numeric(scored_df["y_pred"])
        if "residual" in scored_df.columns:
            dist["residual"] = _describe_numeric(scored_df["residual"])
        # group size distribution (if present)
        if "group_size" in scored_df.columns:
            dist["group_size"] = _describe_numeric(scored_df["group_size"])

    # Confidence counts
    confidence_counts: Dict[str, int] = {}
    if len(scored_df) > 0 and "confidence" in scored_df.columns:
        confidence_counts = scored_df["confidence"].fillna("NA").astype(str).value_counts().to_dict()
        confidence_counts = {str(k): int(v) for k, v in confidence_counts.items()}

    # Basic season/year counts for context (from calving_date)
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


    # --- T4-02: mastitis risk (best-effort, may be absent) ---
    mastitis = {"available": False}
    try:
        m_base = base / "mastitis" / "scoring"
        if m_base.exists():
            runs = sorted([p for p in m_base.iterdir() if p.is_dir()])
            if runs:
                m_run = runs[-1]
                m_sum_path = m_run / "scoring_summary.json"
                m_scores_path = m_run / "mastitis_risk_scores.csv"
                m_expl_path = m_run / "mastitis_explanations.csv"
                m_sum = _read_json(m_sum_path) if m_sum_path.exists() else {}
                m_scores = pd.read_csv(m_scores_path) if m_scores_path.exists() else pd.DataFrame()
                if not m_scores.empty:
                    top_risk_rows = _top_rows(m_scores, n=20)
                    mastitis = {
                        "available": True,
                        "scoring_run": m_run.name,
                        "asof_date": m_sum.get("asof_date"),
                        "horizon_days": m_sum.get("horizon_days"),
                        "risk_threshold": m_sum.get("risk_threshold"),
                        "top_risk": top_risk_rows,
                        "animal_explainability": _build_mastitis_animal_explainability_rows(top_risk_rows),
                        "explainability": _build_mastitis_explainability_summary(top_risk_rows),
                        "paths": {
                            "scoring_summary_json": str(m_sum_path.resolve()),
                            "risk_scores_csv": str(m_scores_path.resolve()),
                            "explanations_csv": str(m_expl_path.resolve()) if m_expl_path.exists() else "NA",
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
            explain_df = explain_df[(explain_df["explain_top_factors_text"].fillna("").astype(str) != "insufficient_explainability_data") | (explain_df.get("explain_counterfactuals_text", pd.Series([], dtype='object')).fillna("").astype(str) != "no_simple_counterfactual")]
            if not explain_df.empty:
                sort_cols = [c for c in ["action", "y_pred"] if c in explain_df.columns]
                if sort_cols:
                    asc = [True if c == "action" else False for c in sort_cols]
                    explain_df = explain_df.sort_values(sort_cols, ascending=asc)
                explain_rows = _top_rows(explain_df, n=20)
        if explain_rows:
            productivity_explainability = {
                "available": True,
                "scoring_run": scoring_run if "scoring_run" in locals() else scoring_summary.get("scoring_run"),
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

    # --- T12-03: Playbooks (recommended plan of actions) ---
    # Best-effort: resolve from web.db (active version) else defaults.yaml.
    farm_ctx: str = ""
    try:
        if mastitis.get("available") and (mastitis.get("top_risk") or []):
            farm_ctx = str((mastitis.get("top_risk") or [])[0].get("farm_id") or "").strip()
    except Exception:
        farm_ctx = ""
    if not farm_ctx:
        try:
            if len(scored_df) > 0 and "farm_id" in scored_df.columns:
                farm_ctx = str(scored_df["farm_id"].dropna().astype(str).head(1).tolist()[0] if not scored_df["farm_id"].dropna().empty else "").strip()
        except Exception:
            farm_ctx = ""

    recommended: List[Dict[str, Any]] = []

    # Mastitis risk playbook if module available
    if mastitis.get("available"):
        pb = resolve_active_playbook(target_kind="alert", target_type="ML.MASTITIS_RISK", farm_id=farm_ctx or None)
        if pb:
            recommended.append(pb)

    # QC generic playbook when QC is not OK
    qc_status = str(fact_pack.get("qc", {}).get("qc_status") or "").upper()
    if qc_status and qc_status not in ("OK", "PASS", "DONE"):
        pb2 = resolve_active_playbook(target_kind="alert", target_type="QC.GENERIC", farm_id=farm_ctx or None)
        if pb2:
            recommended.append(pb2)
        # also include task checklist for data correction (commonly created from QC)
        pb3 = resolve_active_playbook(target_kind="task", target_type="data_correction", farm_id=farm_ctx or None)
        if pb3:
            recommended.append(pb3)

    # De-dupe by (playbook_key, farm_id, version_id)
    uniq: Dict[str, Dict[str, Any]] = {}
    for p in recommended:
        k = f"{p.get('playbook_key','')}|{p.get('farm_id','')}|{p.get('version_id','')}"
        uniq[k] = p

    fact_pack["playbooks"] = {
        "available": bool(uniq),
        "farm_id_context": farm_ctx or "",
        "recommended": list(uniq.values()),
    }

    return fact_pack


def _sanitize_llm_numbers(text: str, fact_pack_str: str) -> str:
    """Ensure generated text doesn't introduce numbers not present in fact_pack.

    This is a pragmatic guardrail (not a perfect verifier), used only in LLM mode.
    """

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        # keep common list bullets like "1." by allowing if followed by '.' and preceding line start
        if tok in fact_pack_str:
            return tok
        return "n/a"

    # match standalone numbers (ints/floats)
    return re.sub(r"\b\d+(?:\.\d+)?\b", repl, text)


build_fact_pack = build_assistant_fact_pack


def generate_report_text_fallback(fact_pack: Dict[str, Any]) -> Dict[str, str]:
    """Backward-compatible wrapper over core assistant reporting narrative builder."""
    return _core_generate_assistant_report_text_fallback(fact_pack)

def generate_report_text_llm(
    fact_pack: Dict[str, Any],
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> Tuple[Dict[str, str], bool, Optional[str]]:
    """Backward-compatible wrapper over core assistant LLM narrative builder."""
    return _core_generate_assistant_report_text_llm(
        fact_pack,
        model=model,
        temperature=temperature,
    )

def _render_docx(
    *,
    fact_pack: Dict[str, Any],
    narrative: Dict[str, str],
    out_path: Path,
    report_version: str,
    llm_used: bool,
) -> None:
    """Backward-compatible wrapper over core assistant DOCX renderer."""
    return _core_render_assistant_report_docx(
        fact_pack=fact_pack,
        narrative=narrative,
        out_path=out_path,
        report_version=report_version,
        llm_used=llm_used,
    )

def _render_pdf(
    *,
    narrative: Dict[str, str],
    fact_pack: Dict[str, Any],
    out_path: Path,
    report_version: str,
    llm_used: bool,
) -> bool:
    """Backward-compatible wrapper over core assistant PDF renderer."""
    return _core_render_assistant_report_pdf(
        narrative=narrative,
        fact_pack=fact_pack,
        out_path=out_path,
        report_version=report_version,
        llm_used=llm_used,
    )

def run_report(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: str,
    scoring_run: str,
    mode: str = "fallback",
    report_version: Optional[str] = None,
    make_pdf: bool = True,
    llm_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible thin wrapper over canonical core reporting entrypoint."""

    return run_assistant_report_use_case(
        artifacts_root=artifacts_root,
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode=mode,
        report_version=report_version,
        make_pdf=make_pdf,
        llm_model=llm_model,
        build_fact_pack=build_fact_pack,
        generate_report_text_fallback=generate_report_text_fallback,
        generate_report_text_llm=(lambda fact_pack: generate_report_text_llm(fact_pack, model=llm_model)),
        render_docx=_render_docx,
        render_pdf=_render_pdf,
        utc_now_iso=_utc_now_iso,
        read_json=_read_json,
        write_json=write_json,
        generate_run_id=generate_run_id,
        get_run_root=get_run_root,
        copy_tree_into_run=copy_tree_into_run,
        write_run_manifest=write_run_manifest,
        write_checksums=write_checksums,
    )
