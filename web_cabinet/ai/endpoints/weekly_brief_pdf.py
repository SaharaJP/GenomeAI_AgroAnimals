"""GET /api/ai/weekly-brief/{brief_id}/pdf — PDF-экспорт недельного брифинга."""
from __future__ import annotations

import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..cache import get_cache
from ..models import WeeklyBrief

logger = logging.getLogger("genomeai.ai.endpoint.weekly_brief_pdf")
router = APIRouter()

_BRAND_TEAL = (0, 150, 136)
_BRAND_DARK = (30, 30, 30)


@router.get("/weekly-brief/{brief_id}/pdf")
async def export_weekly_brief_pdf(
    brief_id: str, farm_id: str = "demo-farm-v1"
) -> StreamingResponse:
    """Генерирует PDF недельного брифинга с брендингом GenomeAI."""
    brief = _load_brief(brief_id, farm_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"brief {brief_id!r} not found")
    pdf_bytes = _render_pdf(brief)
    filename = f"weekly_brief_{brief.period.end}_{farm_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_brief(brief_id: str, farm_id: str) -> Optional[WeeklyBrief]:
    cache = get_cache()
    from .weekly_brief import _default_period, _load_seeded_brief
    start_date, end_date = _default_period()
    cache_key = cache.make_key(
        "weekly_brief", {"farm_id": farm_id, "start": start_date, "end": end_date}
    )
    cached = cache.get(cache_key)
    if cached:
        try:
            b = WeeklyBrief(**json.loads(cached))
            if b.brief_id == brief_id or brief_id == "latest":
                return b
        except Exception:
            pass
    return _load_seeded_brief(farm_id, start_date, end_date)


def _render_pdf(brief: WeeklyBrief) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("reportlab not installed") from exc

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Недельный брифинг GenomeAI — {brief.period.start}..{brief.period.end}",
    )

    styles = getSampleStyleSheet()
    teal = colors.Color(_BRAND_TEAL[0] / 255, _BRAND_TEAL[1] / 255, _BRAND_TEAL[2] / 255)
    dark = colors.Color(_BRAND_DARK[0] / 255, _BRAND_DARK[1] / 255, _BRAND_DARK[2] / 255)

    def style(name: str, **kw: object) -> ParagraphStyle:
        base = styles["Normal"].clone(name)
        for k, v in kw.items():
            setattr(base, k, v)
        return base

    h1 = style("WH1", fontSize=20, textColor=teal, spaceAfter=4, leading=24)
    h2 = style("WH2", fontSize=14, textColor=dark, spaceAfter=2, leading=18)
    h3 = style("WH3", fontSize=11, textColor=teal, spaceAfter=2, leading=14)
    body = style("WBody", fontSize=10, textColor=dark, spaceAfter=4, leading=14)
    hl = style("WHL", fontSize=9, textColor=dark, spaceAfter=2, leading=12)
    caption = style("WCaption", fontSize=8, textColor=colors.grey, spaceAfter=2)

    story: list = []

    # Header
    story.append(Paragraph("GenomeAI · ИИ-помощник", caption))
    story.append(Paragraph(brief.title, h1))
    story.append(Paragraph(
        f"Ферма: {brief.farm_id} · Период: {brief.period.start} — {brief.period.end} · "
        f"Сгенерирован: {brief.generated_at_utc.strftime('%Y-%m-%d %H:%M UTC')}",
        caption,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=teal, spaceAfter=8))

    # Executive summary
    story.append(Paragraph("Резюме недели", h2))
    story.append(Paragraph(brief.executive_summary, body))
    story.append(Spacer(1, 0.3 * cm))

    # KPI table
    if brief.kpi_table:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("KPI недели", h2))
        kpi_rows = [["Показатель", "Факт", "Пред. период", "Δ%", "Ед."]]
        for kpi_name, kpi_val in brief.kpi_table.items():
            if isinstance(kpi_val, dict):
                delta = kpi_val.get("delta_pct", "")
                delta_str = f"{delta:+.1f}%" if isinstance(delta, (int, float)) else str(delta)
                kpi_rows.append([
                    kpi_name,
                    str(kpi_val.get("value", "")),
                    str(kpi_val.get("prev_period", "—")),
                    delta_str,
                    str(kpi_val.get("unit", "")),
                ])
        if len(kpi_rows) > 1:
            tbl = Table(kpi_rows, colWidths=[7 * cm, 2.5 * cm, 2.5 * cm, 2 * cm, 2 * cm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), teal),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.96, 0.98, 0.98)]),
            ]))
            story.append(tbl)
        story.append(Spacer(1, 0.3 * cm))

    # Sections
    for section in brief.sections:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(section.heading, h2))
        for para in section.narrative.split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, body))
        if section.highlights:
            for item in section.highlights:
                story.append(Paragraph(f"• {item}", hl))
        story.append(Spacer(1, 0.2 * cm))

    # Anomalies
    if brief.anomalies_detected:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Выявленные аномалии", h2))
        sev_labels = {"critical": "[КРИТ]", "warning": "[ВНИМАНИЕ]", "info": "[ИНФО]"}
        for anomaly in brief.anomalies_detected:
            label = sev_labels.get(anomaly.severity, f"[{anomaly.severity.upper()}]")
            ev = f" [{anomaly.evidence_id}]" if anomaly.evidence_id else ""
            story.append(Paragraph(f"{label} {anomaly.description}{ev}", body))
        story.append(Spacer(1, 0.3 * cm))

    # Recommendations
    if brief.key_recommendations:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Рекомендации на следующую неделю", h2))
        for i, rec in enumerate(brief.key_recommendations, 1):
            story.append(Paragraph(f"{i}. [{rec.priority.upper()}] {rec.recommendation}", h3))
            story.append(Paragraph(f"Обоснование: {rec.rationale}", body))
            story.append(Paragraph(f"Ожидаемый результат: {rec.expected_outcome}", body))
            if rec.affected_entities:
                story.append(Paragraph(f"Объекты: {', '.join(rec.affected_entities)}", hl))
            story.append(Spacer(1, 0.15 * cm))

    # Footer
    story.append(HRFlowable(width="100%", thickness=2, color=teal, spaceBefore=8))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        f"Модель: {brief.generation_model} · "
        f"Токены: {brief.generation_tokens.get('input', 0)}↑ / {brief.generation_tokens.get('output', 0)}↓",
        caption,
    ))

    doc.build(story)
    return buf.getvalue()
