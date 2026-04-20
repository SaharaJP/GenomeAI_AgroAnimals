from __future__ import annotations

"""T8-01: Регулярные AI-отчёты (daily/weekly) по модульному шаблону.

Это модуль *offline-core*.

Принципы:
1) Источник правды — только fact_pack.json (агрегаты/витрины/алерты/выгрузки).
2) Никаких "диагнозов" — только риск/факты/действия.
3) У каждого блока указаны источники (пути к артефактам).
4) LLM (опционально) обязан следовать fact_pack; есть fallback без LLM.

Артефакты:
  artifacts/<data_version>/reports_regular/<report_version>/
    - fact_pack.json
    - report_summary.json
    - exports/report_director.md
    - exports/report_director.html
    - exports/report_director.pdf
    - exports/report_ops.md
    - exports/report_ops.html
    - exports/report_ops.pdf

Ограничения текущей итерации:
 - В fact_pack подтягиваем модули best-effort: KPI, alerts_v2, repro, mating_plan, economics, mastitis.
 - Если модульных артефактов нет — секция помечается как NA (и это отражается в sources).
"""

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.application.ml_artifacts import find_latest_model_version
from core.reporting.fact_pack import build_regular_fact_pack
from core.reporting.regular_reporting import (
    generate_regular_report_text_fallback as _core_generate_regular_report_text_fallback,
    generate_regular_report_text_llm as _core_generate_regular_report_text_llm,
    render_regular_report_markdown as _core_render_regular_report_markdown,
)
from core.reporting.report_builder import write_markdown_report_bundle
from core.reporting.entrypoints import run_regular_report as _core_run_regular_report
def run_regular_report_use_case(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str = "daily",
    mode: str = "fallback",
    llm_model: Optional[str] = None,
    report_version: Optional[str] = None,
    **_ignored: Any,
) -> Dict[str, Any]:
    """Compatibility adapter preserving old use-case injection surface."""
    return _core_run_regular_report(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        period=period,
        mode=mode,
        llm_model=llm_model,
        report_version=report_version,
    )


from .alerts_v2 import generate_alerts_v2
from .playbooks import resolve_active_playbook
from .versioning import compute_data_version, generate_run_id, write_json


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
    """KPI v2 writes into artifacts/<dv>/runs/<run_id>/kpi/"""
    runs_root = Path(artifacts_root) / data_version / "runs"
    if not runs_root.exists():
        return None
    candidates: List[Path] = []
    for r in runs_root.iterdir():
        if not r.is_dir():
            continue
        if (r / "kpi" / "kpi_summary.json").exists():
            candidates.append(r)
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


def _top_rows(df: pd.DataFrame, n: int = 20, cols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    out = df.head(n)
    if cols:
        keep = [c for c in cols if c in out.columns]
        if keep:
            out = out[keep]
    return json.loads(out.fillna("").to_json(orient="records", force_ascii=False))


def _sanitize_llm_numbers(text: str, fact_pack_str: str) -> str:
    """Pragmatic guardrail: remove numbers not present in fact_pack."""

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if tok in fact_pack_str:
            return tok
        return "n/a"

    return re.sub(r"\b\d+(?:\.\d+)?\b", repl, text)



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

def build_fact_pack_regular(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str,
    max_rows: int = 20,
) -> Dict[str, Any]:
    """Сбор единого fact-pack из модульных витрин/артефактов."""

    artifacts_root = Path(artifacts_root).resolve()
    dv = str(data_version)

    # --- KPI (T3/T4): best-effort load latest ---
    kpi_block: Dict[str, Any] = {"available": False}
    kpi_run_root = _find_latest_kpi_run_root(artifacts_root, dv)
    if kpi_run_root is not None:
        kpi_dir = kpi_run_root / "kpi"
        kpi_sum = _read_json(kpi_dir / "kpi_summary.json") if (kpi_dir / "kpi_summary.json").exists() else {}
        kpi_wide = _safe_read_csv(kpi_dir / "kpi_wide.csv")
        kpi_alerts = _safe_read_csv(kpi_dir / "kpi_alerts.csv")
        kpi_block = {
            "available": True,
            "run_id": kpi_sum.get("run_id", kpi_run_root.name),
            "asof_date": kpi_sum.get("asof_date", asof_date),
            "currency": kpi_sum.get("currency", "NA"),
            "kpi_count": kpi_sum.get("kpi_count", int(kpi_wide.shape[0]) if not kpi_wide.empty else 0),
            "alert_count": kpi_sum.get("alert_count", int(kpi_alerts.shape[0]) if not kpi_alerts.empty else 0),
            "kpi_wide_top": _top_rows(kpi_wide, n=max_rows),
            "kpi_alerts_top": _top_rows(kpi_alerts, n=max_rows),
            "sources": {
                "kpi_summary": str((kpi_dir / "kpi_summary.json").resolve()) if (kpi_dir / "kpi_summary.json").exists() else "NA",
                "kpi_wide": str((kpi_dir / "kpi_wide.csv").resolve()) if (kpi_dir / "kpi_wide.csv").exists() else "NA",
                "kpi_alerts": str((kpi_dir / "kpi_alerts.csv").resolve()) if (kpi_dir / "kpi_alerts.csv").exists() else "NA",
            },
        }

    # --- Reproduction (T5-01) ---
    repro_block: Dict[str, Any] = {"available": False}
    repro_root = artifacts_root / dv / "repro" / "runs"
    repro_run = _latest_dir(repro_root)
    if repro_run is not None:
        man = _read_json(repro_run / "run_manifest.json") if (repro_run / "run_manifest.json").exists() else {}
        kpis = _safe_read_csv(repro_run / "repro_kpis_farm.csv")
        wls = _safe_read_csv(repro_run / "repro_worklists.csv")
        repro_block = {
            "available": True,
            "run_id": man.get("run_id", repro_run.name),
            "asof_date": (man.get("params", {}) or {}).get("asof_date", "NA"),
            "kpis_top": _top_rows(kpis, n=max_rows),
            "worklists_counts": (wls["worklist_type"].value_counts().to_dict() if (not wls.empty and "worklist_type" in wls.columns) else {}),
            "worklists_top": _top_rows(wls.sort_values(["priority"], ascending=[True]) if (not wls.empty and "priority" in wls.columns) else wls, n=max_rows),
            "sources": {
                "run_manifest": str((repro_run / "run_manifest.json").resolve()) if (repro_run / "run_manifest.json").exists() else "NA",
                "kpis_csv": str((repro_run / "repro_kpis_farm.csv").resolve()) if (repro_run / "repro_kpis_farm.csv").exists() else "NA",
                "worklists_csv": str((repro_run / "repro_worklists.csv").resolve()) if (repro_run / "repro_worklists.csv").exists() else "NA",
                "xlsx": str((repro_run / "repro_kpi_worklists.xlsx").resolve()) if (repro_run / "repro_kpi_worklists.xlsx").exists() else "NA",
            },
        }

    # --- Mating plan (T6-02) ---
    mating_block: Dict[str, Any] = {"available": False}
    mp_root = artifacts_root / dv / "mating_plan"
    mp_run = _latest_dir(mp_root)
    if mp_run is not None:
        summary = _read_json(mp_run / "summary.json") if (mp_run / "summary.json").exists() else {}
        mp_df = _safe_read_csv(mp_run / "mating_plan.csv")
        mating_block = {
            "available": True,
            "run_id": summary.get("mating_plan_run", mp_run.name),
            "counts": summary.get("counts", {}),
            "top_pairs": _top_rows(mp_df, n=max_rows),
            "sources": {
                "summary_json": str((mp_run / "summary.json").resolve()) if (mp_run / "summary.json").exists() else "NA",
                "mating_plan_csv": str((mp_run / "mating_plan.csv").resolve()) if (mp_run / "mating_plan.csv").exists() else "NA",
                "mating_plan_xlsx": str((mp_run / "mating_plan.xlsx").resolve()) if (mp_run / "mating_plan.xlsx").exists() else "NA",
            },
        }

    # --- Economics what-if (T7-01) ---
    econ_block: Dict[str, Any] = {"available": False}
    econ_root = artifacts_root / dv / "economics"
    econ_run = _latest_dir(econ_root)
    if econ_run is not None:
        summary_farm = _safe_read_csv(econ_run / "summary_farm.csv")
        params = {}
        if (econ_run / "whatif_params.json").exists():
            try:
                params = _read_json(econ_run / "whatif_params.json")
            except Exception:
                params = {}
        econ_block = {
            "available": True,
            "economics_run": econ_run.name,
            "params": params,
            "summary_farm_top": _top_rows(summary_farm, n=max_rows),
            "sources": {
                "summary_farm": str((econ_run / "summary_farm.csv").resolve()) if (econ_run / "summary_farm.csv").exists() else "NA",
                "xlsx": str((econ_run / "economics_whatif.xlsx").resolve()) if (econ_run / "economics_whatif.xlsx").exists() else "NA",
                "whatif_params": str((econ_run / "whatif_params.json").resolve()) if (econ_run / "whatif_params.json").exists() else "NA",
            },
        }

    # --- Health: mastitis risk (T4-02) best-effort ---
    mastitis: Dict[str, Any] = {"available": False}
    try:
        score_base = artifacts_root / dv / "mastitis" / "scoring"
        m_run = _latest_dir(score_base)
        if m_run is not None:
            m_sum = _read_json(m_run / "scoring_summary.json") if (m_run / "scoring_summary.json").exists() else {}
            m_scores = _safe_read_csv(m_run / "mastitis_risk_scores.csv")
            m_expl = m_run / "mastitis_explanations.csv"
            top_risk_rows = _top_rows(m_scores, n=max_rows)
            mastitis = {
                "available": True,
                "scoring_run": m_run.name,
                "asof_date": m_sum.get("asof_date"),
                "horizon_days": m_sum.get("horizon_days"),
                "risk_threshold": m_sum.get("risk_threshold"),
                "top_risk": top_risk_rows,
                "animal_explainability": _build_mastitis_animal_explainability_rows(top_risk_rows, max_rows=max_rows),
                "explainability": _build_mastitis_explainability_summary(top_risk_rows, max_rows=max_rows),
                "sources": {
                    "scoring_summary_json": str((m_run / "scoring_summary.json").resolve()) if (m_run / "scoring_summary.json").exists() else "NA",
                    "risk_scores_csv": str((m_run / "mastitis_risk_scores.csv").resolve()) if (m_run / "mastitis_risk_scores.csv").exists() else "NA",
                    "explanations_csv": str(m_expl.resolve()) if m_expl.exists() else "NA",
                },
            }
    except Exception:
        mastitis = {"available": False}

    # --- Alerts v2 (deterministic generators) ---
    alerts: List[Dict[str, Any]] = []
    try:
        today = datetime.strptime(asof_date, "%Y-%m-%d").date()
    except Exception:
        today = _date.today()
    try:
        alerts = generate_alerts_v2(artifacts_root=artifacts_root, data_version=dv, today=today)
    except Exception:
        alerts = []

    # --- T12-03: Playbooks for top alert types (best-effort) ---
    pb_items: List[Dict[str, Any]] = []
    try:
        top_alerts = alerts[: min(len(alerts), 10)]
        uniq_types: List[str] = []
        for a in top_alerts:
            at = str(a.get("alert_type") or "").strip()
            if at and at not in uniq_types:
                uniq_types.append(at)
        for at in uniq_types[:10]:
            pb = resolve_active_playbook(target_kind="alert", target_type=at, farm_id=None)
            if pb:
                pb_items.append(pb)
        # Ensure mastitis playbook appears if mastitis module available
        if mastitis.get("available"):
            pbm = resolve_active_playbook(target_kind="alert", target_type="ML.MASTITIS_RISK", farm_id=None)
            if pbm:
                pb_items.append(pbm)
    except Exception:
        pb_items = []

    # de-dupe
    pb_uniq: Dict[str, Dict[str, Any]] = {}
    for p in pb_items:
        k = f"{p.get('playbook_key','')}|{p.get('farm_id','')}|{p.get('version_id','')}"
        pb_uniq[k] = p
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
            "economics": econ_block,
        },
        "disclaimer": (
            "Decision-support: отчёт носит рекомендательный характер. "
            "Не является диагнозом или ветеринарным заключением. "
            "Все цифры и списки получены из витрин/алертов и указаны с источниками."
        ),
    }
    return fact_pack


def _fmt_kv_lines(d: Dict[str, Any], keys: List[str]) -> List[str]:
    out: List[str] = []
    for k in keys:
        out.append(f"- {k}: {d.get(k, 'NA')}")
    return out


build_fact_pack_regular = build_regular_fact_pack


def generate_regular_report_text_fallback(fact_pack: Dict[str, Any], *, audience: str) -> Dict[str, str]:
    """Backward-compatible wrapper over core regular-report fallback narrative."""
    return _core_generate_regular_report_text_fallback(fact_pack, audience=audience)

def generate_regular_report_text_llm(
    fact_pack: Dict[str, Any],
    *,
    audience: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> Tuple[Dict[str, str], bool, Optional[str]]:
    """Backward-compatible wrapper over core LLM narrative."""
    return _core_generate_regular_report_text_llm(
        fact_pack,
        audience=audience,
        model=model,
        temperature=temperature,
    )

def _render_md(
    *,
    narrative: Dict[str, str],
    fact_pack: Dict[str, Any],
    out_path: Path,
    report_version: str,
    audience: str,
    llm_used: bool,
) -> None:
    """Backward-compatible wrapper over core markdown renderer."""
    return _core_render_regular_report_markdown(
        narrative=narrative,
        fact_pack=fact_pack,
        out_path=out_path,
        report_version=report_version,
        audience=audience,
        llm_used=llm_used,
    )

def _render_html_from_md(md_text: str) -> str:
    """Лёгкий рендер в HTML (без сторонних зависимостей)."""
    # Minimal conversion: headings + code blocks + paragraphs.
    html_lines: List[str] = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        "<style>body{font-family:Arial,Helvetica,sans-serif;margin:24px;} pre{background:#f6f8fa;padding:12px;overflow:auto;} table{border-collapse:collapse;} td,th{border:1px solid #ddd;padding:6px;} h1,h2,h3{margin-top:18px;}</style>",
        "</head><body>",
    ]
    in_code = False
    for line in md_text.splitlines():
        if line.strip().startswith("```"):
            if not in_code:
                html_lines.append("<pre>")
                in_code = True
            else:
                html_lines.append("</pre>")
                in_code = False
            continue
        if in_code:
            html_lines.append(
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            continue
        if line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.strip() == "---":
            html_lines.append("<hr/>")
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            # likely markdown table - keep in <pre> (simple and robust)
            html_lines.append(f"<pre>{line}</pre>")
        elif line.strip() == "":
            html_lines.append("<br/>")
        else:
            html_lines.append(f"<p>{line}</p>")
    if in_code:
        html_lines.append("</pre>")
    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def _render_pdf_simple(
    *,
    title: str,
    md_text: str,
    out_path: Path,
) -> bool:
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.units import cm  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except Exception:
        return False

    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        font_name = "DejaVu"
    except Exception:
        font_name = "Helvetica"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    x = 2 * cm
    y = h - 2 * cm
    c.setFont(font_name, 14)
    c.drawString(x, y, title[:120])
    y -= 1 * cm
    c.setFont(font_name, 10)
    for raw in md_text.splitlines():
        line = raw.strip("\n")
        if y < 2 * cm:
            c.showPage()
            y = h - 2 * cm
            c.setFont(font_name, 10)
        # avoid very long lines
        c.drawString(x, y, line[:140])
        y -= 0.45 * cm
    c.save()
    return True


@dataclass
class RegularReportSummary:
    schema: str
    created_at_utc: str
    data_version: str
    model_version: str
    report_version: str
    period: str
    asof_date: str
    mode_requested: str
    llm_used: bool
    inputs: Dict[str, Any]
    outputs: Dict[str, str]


def run_regular_report(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str = "daily",
    mode: str = "fallback",
    llm_model: Optional[str] = None,
    report_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible thin wrapper over canonical core reporting entrypoint."""

    return run_regular_report_use_case(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        period=period,
        mode=mode,
        llm_model=llm_model,
        report_version=report_version,
        build_fact_pack=build_fact_pack_regular,
        generate_report_text_fallback=(lambda fact_pack, audience: generate_regular_report_text_fallback(fact_pack, audience=audience)),
        generate_report_text_llm=(lambda fact_pack, audience: generate_regular_report_text_llm(fact_pack, audience=audience, model=llm_model)),
        render_md=_render_md,
        utc_now_iso=_utc_now_iso,
        generate_run_id=generate_run_id,
        write_json=write_json,
    )
