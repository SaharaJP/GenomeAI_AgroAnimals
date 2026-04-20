from __future__ import annotations

"""T11-04: What-If 2.0 — PDF отчёт по сценарию.

Ключевые принципы:
 - UI (Streamlit/Web Cabinet) ничего не считает.
 - Отчёт строится строго из фактов/таблиц/метрик, уже рассчитанных offline-core.
 - LLM не используется (это отдельный контур AI-отчётов).

Артефакты:
  artifacts/<data_version>/whatif_reports/<report_version>/
    - whatif_report.pdf
    - report_meta.json
    - manifest.json
    - checksums.json

Отчёт включает:
 - Контекст (data_version, период, cfg_path)
 - Предпосылки (мультипликаторы сценария)
 - Формулы (прозрачные)
 - Итоги BASE vs SCENARIO + дельты
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from .economics_whatif import load_economics
from .versioning import generate_run_id, write_checksums, write_json


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fmt_money(x: float) -> str:
    try:
        return f"{float(x):,.2f}".replace(",", " ")
    except Exception:
        return str(x)


def _totals_from_summary_farm(sum_farm: pd.DataFrame | None, *, mode: str = "scenario") -> dict[str, float]:
    """Totals from summary_farm.

    mode:
      - 'baseline' uses *_baseline columns
      - 'scenario' uses *_scenario columns
      - fallback to non-suffixed columns if present
    """
    if sum_farm is None or getattr(sum_farm, "empty", True):
        return {"revenue": 0.0, "total_cost": 0.0, "margin": 0.0, "margin_pct": 0.0}

    df = sum_farm
    suf = "_baseline" if mode == "baseline" else "_scenario"

    def pick(base: str) -> str | None:
        if f"{base}{suf}" in df.columns:
            return f"{base}{suf}"
        if base in df.columns:
            return base
        return None

    c_rev = pick("revenue")
    c_cost = pick("total_cost")
    c_margin = pick("margin")
    if not c_rev or not c_cost or not c_margin:
        return {"revenue": 0.0, "total_cost": 0.0, "margin": 0.0, "margin_pct": 0.0}

    revenue = float(pd.to_numeric(df[c_rev], errors="coerce").fillna(0.0).sum())
    total_cost = float(pd.to_numeric(df[c_cost], errors="coerce").fillna(0.0).sum())
    margin = float(pd.to_numeric(df[c_margin], errors="coerce").fillna(0.0).sum())
    margin_pct = (margin / revenue) if revenue > 0 else 0.0
    return {"revenue": revenue, "total_cost": total_cost, "margin": margin, "margin_pct": float(margin_pct)}


def _write_pdf(
    *,
    out_pdf: Path,
    title: str,
    meta: dict[str, Any],
    base_tot: dict[str, float],
    scen_tot: dict[str, float],
) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(str(out_pdf), pagesize=A4, title=title)
    story: list[Any] = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    # Context
    ctx_lines = [
        f"<b>data_version:</b> {meta.get('data_version')}",
        f"<b>period:</b> {meta.get('date_from')} .. {meta.get('date_to')}",
        f"<b>cfg_path:</b> {meta.get('cfg_path')}",
        f"<b>base_economics_run:</b> {meta.get('base_economics_run')}",
        f"<b>scenario_economics_run:</b> {meta.get('scenario_economics_run')}",
        f"<b>report_version:</b> {meta.get('report_version')}",
        f"<b>generated_at:</b> {meta.get('generated_at_utc')}",
    ]

    # Optional governance info (approval/archive), if provided by caller
    g = meta.get("scenario_meta") or {}
    if g:
        ctx_lines.append(f"<b>scenario_status:</b> {g.get('status')}")
        if g.get("approved_at") or g.get("approved_by_username"):
            ctx_lines.append(f"<b>approved_at:</b> {g.get('approved_at')}")
            ctx_lines.append(f"<b>approved_by:</b> {g.get('approved_by_username')}")
        if g.get("approval_comment"):
            ctx_lines.append(f"<b>approval_comment:</b> {g.get('approval_comment')}")
        if g.get("cloned_from_scenario_id"):
            ctx_lines.append(f"<b>cloned_from:</b> {g.get('cloned_from_scenario_id')}")
        if g.get("archived_at") or g.get("archived_by_username"):
            ctx_lines.append(f"<b>archived_at:</b> {g.get('archived_at')}")
            ctx_lines.append(f"<b>archived_by:</b> {g.get('archived_by_username')}")
        if g.get("archive_comment"):
            ctx_lines.append(f"<b>archive_comment:</b> {g.get('archive_comment')}")
    story.append(Paragraph("<b>Контекст</b>", styles["Heading2"]))
    story.append(Paragraph("<br/>".join(ctx_lines), styles["BodyText"]))
    story.append(Spacer(1, 10))

    # Assumptions
    p = meta.get("scenario_params") or {}
    story.append(Paragraph("<b>Предпосылки (параметры сценария)</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            "<br/>".join(
                [
                    f"<b>scenario_name:</b> {meta.get('scenario_name')}",
                    f"<b>scenario_id:</b> {meta.get('scenario_id')}",
                    f"<b>milk_price_multiplier:</b> {p.get('milk_price_multiplier', 1.0)}",
                    f"<b>feed_cost_multiplier:</b> {p.get('feed_cost_multiplier', 1.0)}",
                    f"<b>other_cost_multiplier:</b> {p.get('other_cost_multiplier', 1.0)}",
                ]
            ),
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 10))

    # Formulas
    story.append(Paragraph("<b>Формулы (прозрачные)</b>", styles["Heading2"]))
    formulas = [
        "Выручка (revenue) = Σ(milk_kg × milk_price_per_kg)",
        "Затраты на корм (feed_cost) = Σ(feed_dm_kg × feed_cost_per_kg_dm)",
        "Прочие затраты (other_cost) = Σ(other_cost_per_farm_day)",
        "Итого затраты (total_cost) = feed_cost + other_cost",
        "Маржа (margin) = revenue − total_cost",
        "Маржа % (margin_pct) = margin / revenue (если revenue>0)",
        "Сценарий what-if применяет мультипликаторы к базовым ценам/затратам:",
        "  milk_price = milk_price × milk_price_multiplier",
        "  feed_cost  = feed_cost × feed_cost_multiplier",
        "  other_cost = other_cost × other_cost_multiplier",
    ]
    story.append(Paragraph("<br/>".join(formulas), styles["BodyText"]))
    story.append(Spacer(1, 10))

    # Totals table
    story.append(Paragraph("<b>Итоги (BASE vs SCENARIO)</b>", styles["Heading2"]))
    delta = {
        "revenue": scen_tot["revenue"] - base_tot["revenue"],
        "total_cost": scen_tot["total_cost"] - base_tot["total_cost"],
        "margin": scen_tot["margin"] - base_tot["margin"],
        "margin_pct": scen_tot["margin_pct"] - base_tot["margin_pct"],
    }
    data = [
        ["Метрика", "BASE", "SCENARIO", "Δ (SCENARIO−BASE)"],
        ["Revenue", _fmt_money(base_tot["revenue"]), _fmt_money(scen_tot["revenue"]), _fmt_money(delta["revenue"])],
        ["Total cost", _fmt_money(base_tot["total_cost"]), _fmt_money(scen_tot["total_cost"]), _fmt_money(delta["total_cost"])],
        ["Margin", _fmt_money(base_tot["margin"]), _fmt_money(scen_tot["margin"]), _fmt_money(delta["margin"])],
        ["Margin %", f"{base_tot['margin_pct']*100:.2f}%", f"{scen_tot['margin_pct']*100:.2f}%", f"{delta['margin_pct']*100:.2f}%"],
    ]
    tbl = Table(data, hAlign="LEFT")
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 10))

    # Disclaimers
    story.append(Paragraph("<b>Дисклеймер</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            "Отчёт носит decision-support характер и построен на данных и конфигурации, доступных системе. "
            "Фактический экономический эффект зависит от множества факторов (качество данных, дисциплина учёта, "
            "реальные цены/затраты, сезонность) и требует проверки на пилоте.",
            styles["BodyText"],
        )
    )

    doc.build(story)


def generate_whatif_report_pdf(
    *,
    artifacts_root: Path,
    data_version: str,
    scenario_id: str,
    scenario_name: str,
    scenario_params: dict[str, Any],
    scenario_meta: dict[str, Any] | None = None,
    date_from: str,
    date_to: str,
    cfg_path: str,
    base_economics_run: str,
    scenario_economics_run: str,
    report_version: str | None = None,
) -> dict[str, Any]:
    """Generate and store PDF report for a what-if scenario.

    This function **does not** run economics calculations; it only reads existing
    artifacts and produces a reproducible PDF + metadata.
    """

    report_version = report_version or generate_run_id(prefix="whatifrep")
    out_dir = Path(artifacts_root) / data_version / "whatif_reports" / report_version
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load totals from artifacts.
    # Preferred mode: scenario run contains both baseline and scenario summaries.
    if base_economics_run == scenario_economics_run:
        _, dfs = load_economics(
            artifacts_root=artifacts_root,
            data_version=data_version,
            economics_run=scenario_economics_run,
        )
        base_tot = _totals_from_summary_farm(dfs.get("summary_farm"), mode="baseline")
        scen_tot = _totals_from_summary_farm(dfs.get("summary_farm"), mode="scenario")
    else:
        _, base_dfs = load_economics(artifacts_root=artifacts_root, data_version=data_version, economics_run=base_economics_run)
        _, scen_dfs = load_economics(artifacts_root=artifacts_root, data_version=data_version, economics_run=scenario_economics_run)
        base_tot = _totals_from_summary_farm(base_dfs.get("summary_farm"), mode="scenario")
        scen_tot = _totals_from_summary_farm(scen_dfs.get("summary_farm"), mode="scenario")

    meta = {
        "schema": "genomeai.whatif_report.v1",
        "report_version": report_version,
        "generated_at_utc": _utc_ts(),
        "data_version": data_version,
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "scenario_params": scenario_params,
        "scenario_meta": (scenario_meta or {}),
        "date_from": date_from,
        "date_to": date_to,
        "cfg_path": cfg_path,
        "base_economics_run": base_economics_run,
        "scenario_economics_run": scenario_economics_run,
        "totals": {
            "base": base_tot,
            "scenario": scen_tot,
            "delta": {
                "revenue": scen_tot["revenue"] - base_tot["revenue"],
                "total_cost": scen_tot["total_cost"] - base_tot["total_cost"],
                "margin": scen_tot["margin"] - base_tot["margin"],
                "margin_pct": scen_tot["margin_pct"] - base_tot["margin_pct"],
            },
        },
    }

    pdf_path = out_dir / "whatif_report.pdf"
    _write_pdf(
        out_pdf=pdf_path,
        title=f"What-If Report — {scenario_name}",
        meta=meta,
        base_tot=base_tot,
        scen_tot=scen_tot,
    )

    write_json(out_dir / "report_meta.json", meta)
    write_json(
        out_dir / "manifest.json",
        {
            "schema": "genomeai.manifest.v1",
            "created_at": meta["generated_at_utc"],
            "data_version": data_version,
            "report_version": report_version,
            "files": [
                "whatif_report.pdf",
                "report_meta.json",
                "manifest.json",
                "checksums.json",
            ],
        },
    )
    write_checksums(run_root=out_dir)

    return {
        "ok": True,
        "report_version": report_version,
        "data_version": data_version,
        "report_dir": str(out_dir),
        "pdf_path": str(pdf_path),
        "base_economics_run": base_economics_run,
        "scenario_economics_run": scenario_economics_run,
    }
