from __future__ import annotations

"""Template-based report generation (offline-core).

T10-04 Step2: report templates -> generate report artifacts (MD/HTML/PDF)
from a stored template (sections + metrics).

Important: Web/UI is responsible only for *selecting* a template and
providing factual inputs (alerts/tasks/decisions lists). This module
renders a report strictly from those facts + artifacts.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, date as _date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .versioning import generate_run_id, write_json
from core.reporting.template_reporting import prepare_template_report_artifacts
from core.reporting.entrypoints import run_template_report as _core_run_template_report
def run_template_report_use_case(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    mode: str = "fallback",
    report_version: Optional[str] = None,
    **_ignored: Any,
) -> Dict[str, Any]:
    """Compatibility adapter preserving old use-case injection surface."""
    template = _ignored.get("template") or {}
    inputs = _ignored.get("inputs")
    llm_model = _ignored.get("llm_model")
    max_rows = int(_ignored.get("max_rows", 20) or 20)
    options_override = _ignored.get("options_override")
    return _core_run_template_report(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        template=template,
        inputs=inputs,
        mode=mode,
        llm_model=llm_model,
        report_version=report_version,
        max_rows=max_rows,
        options_override=options_override,
    )



def _economics_snapshot_table(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    focus_type: str,
    focus_id: str,
    max_rows: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Best-effort snapshot from economics_v2 artifacts.

    Returns: (meta, df)
      meta: {available, economics_run, date_selected, note}
      df:   rows for selected scope/date with key metrics.
    """

    meta: dict[str, Any] = {"available": False, "economics_run": "", "date_selected": "", "note": ""}
    try:
        rid, dfs, _ = load_economics_v2(artifacts_root=artifacts_root, data_version=str(data_version), economics_run=None)
    except Exception as e:
        meta["note"] = f"no economics_v2: {e}"
        return meta, pd.DataFrame()

    daily = dfs.get("economics_daily")
    if daily is None or daily.empty:
        meta.update({"available": False, "economics_run": rid, "note": "economics_daily пуст"})
        return meta, pd.DataFrame()

    df = daily.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Pick last date <= asof_date (or last available)
    try:
        ad = pd.to_datetime(asof_date, errors="coerce")
    except Exception:
        ad = pd.NaT
    if "date" in df.columns and not df["date"].isna().all():
        if pd.notna(ad):
            candidates = df[df["date"] <= ad]
            dsel = candidates["date"].max() if not candidates.empty else df["date"].max()
        else:
            dsel = df["date"].max()
        df = df[df["date"] == dsel].copy()
        meta["date_selected"] = str(getattr(dsel, "date", lambda: dsel)()) if hasattr(dsel, "date") else str(dsel)

    ft = (focus_type or "").strip().lower()
    fid = (focus_id or "").strip()

    # Scope filter (economics_v2 is pen/site/farm; for animal we fallback to pen of KPI (best-effort) in other sections)
    if ft in {"group", "pen"} and fid and "level" in df.columns and "pen_id" in df.columns:
        df = df[(df["level"] == "pen") & (df["pen_id"].astype(str) == str(fid))].copy()
    elif ft == "farm" and fid and "level" in df.columns and "farm_id" in df.columns:
        df = df[(df["level"] == "farm") & (df["farm_id"].astype(str) == str(fid))].copy()
    elif ft == "site" and fid and "level" in df.columns and "site_id" in df.columns:
        df = df[(df["level"] == "site") & (df["site_id"].astype(str) == str(fid))].copy()
    else:
        # default: show farm level (all farms)
        if "level" in df.columns:
            df = df[df["level"] == "farm"].copy()

    keep = [
        c
        for c in [
            "date",
            "level",
            "farm_id",
            "site_id",
            "pen_id",
            "milk_liters",
            "revenue_total_rub",
            "total_cost_rub",
            "margin_rub",
            "margin_pct",
            "cost_per_liter_rub",
        ]
        if c in df.columns
    ]
    if keep:
        df = df[keep].copy()

    # stable order
    sort_cols = [c for c in ["farm_id", "site_id", "pen_id"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    if len(df) > max_rows:
        df = df.head(max_rows)

    meta.update({"available": True, "economics_run": rid, "note": ""})
    return meta, df


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_date(x: str) -> _date:
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return _date.today()


def _top_rows(records: List[dict], n: int = 20) -> List[dict]:
    out: List[dict] = []
    for r in records[:n]:
        if isinstance(r, dict):
            out.append(r)
    return out


def _render_html_from_md(md_text: str) -> str:
    # Minimal conversion (no external deps).
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
            html_lines.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue
        if line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.strip() == "---":
            html_lines.append("<hr/>")
        elif line.strip() == "":
            html_lines.append("<br/>")
        else:
            # keep markdown tables as-is; browsers still show monospaced blocks
            if line.strip().startswith("|") and line.strip().endswith("|"):
                html_lines.append(f"<pre>{line}</pre>")
            else:
                html_lines.append(f"<p>{line}</p>")
    if in_code:
        html_lines.append("</pre>")
    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def _render_pdf_simple(*, title: str, md_text: str, out_path: Path) -> bool:
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
        c.drawString(x, y, line[:140])
        y -= 0.45 * cm
    c.save()
    return True


def _kpi_table_from_artifacts(*, artifacts_root: Path, data_version: str, metrics: list[str]) -> pd.DataFrame:
    """Best-effort pick metric values from latest KPI wide table."""
    # Locate latest KPI run similar to regular report logic: artifacts/<dv>/<run_id>/kpi/kpi_wide.csv
    base = Path(artifacts_root) / str(data_version)
    # heuristic: search for */kpi/kpi_wide.csv and pick newest by mtime
    candidates: list[Path] = []
    try:
        for p in base.rglob("kpi_wide.csv"):
            if p.is_file() and p.parent.name == "kpi":
                candidates.append(p)
    except Exception:
        candidates = []
    if not candidates:
        return pd.DataFrame(columns=["kpi_id", "value", "unit"])  # empty

    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    kpi_wide_path = candidates[-1]
    try:
        df = pd.read_csv(kpi_wide_path)
    except Exception:
        return pd.DataFrame(columns=["kpi_id", "value", "unit"])

    if df.empty:
        return pd.DataFrame(columns=["kpi_id", "value", "unit"])

    for c in ["kpi_id", "value"]:
        if c not in df.columns:
            return pd.DataFrame(columns=["kpi_id", "value", "unit"])
    if "unit" not in df.columns:
        df["unit"] = ""

    df["kpi_id"] = df["kpi_id"].astype(str)
    df = df.set_index("kpi_id")

    rows = []
    for mid in metrics:
        mid = str(mid)
        if mid in df.index:
            r = df.loc[mid]
            # if duplicated ids, take first
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            rows.append({"kpi_id": mid, "value": r.get("value"), "unit": r.get("unit", "")})
        else:
            rows.append({"kpi_id": mid, "value": "NA", "unit": ""})
    return pd.DataFrame(rows)


def _md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "NA"
    try:
        return df.to_markdown(index=False)
    except Exception:
        # fallback simple
        return df.head(50).to_csv(index=False)


def _sanitize_template(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": str(t.get("template_id") or ""),
        "name": str(t.get("name") or ""),
        "scope": str(t.get("scope") or "user"),
        "sections": list(t.get("sections") or []),
        "metrics": list(t.get("metrics") or []),
        "options": dict(t.get("options") or {}),
    }


@dataclass
class TemplateReportSummary:
    schema: str
    created_at_utc: str
    data_version: str
    report_version: str
    template_id: str
    asof_date: str
    mode_requested: str
    llm_used: bool
    inputs: Dict[str, Any]
    outputs: Dict[str, str]


def _prepare_template_report_artifacts_for_core(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    report_version: str,
    out_dir: Path,
    exports_dir: Path,
    template: dict[str, Any],
    inputs: Optional[dict[str, Any]],
    mode: str,
    max_rows: int,
    options_override: Optional[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Backward-compatible wrapper over core template report preparation."""
    return prepare_template_report_artifacts(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        report_version=report_version,
        out_dir=out_dir,
        exports_dir=exports_dir,
        template=template,
        inputs=inputs,
        mode=mode,
        max_rows=max_rows,
        options_override=options_override,
    )

def run_template_report(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    template: dict[str, Any],
    inputs: Optional[dict[str, Any]] = None,
    mode: str = "fallback",
    llm_model: Optional[str] = None,
    report_version: Optional[str] = None,
    max_rows: int = 20,
    options_override: Optional[dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Backward-compatible thin wrapper over canonical core reporting entrypoint."""
    return run_template_report_use_case(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        mode=mode,
        report_version=report_version,
        llm_model=llm_model,
        template=template,
        inputs=inputs,
        max_rows=max_rows,
        options_override=options_override,
        generate_run_id=generate_run_id,
        utc_now_iso=_utc_now_iso,
        write_json=write_json,
        prepare_fact_pack_and_markdown=(
            lambda **kwargs: _prepare_template_report_artifacts_for_core(
                **kwargs,
                template=template,
                inputs=inputs,
                mode=mode,
                max_rows=max_rows,
                options_override=options_override,
            )
        ),
    )
