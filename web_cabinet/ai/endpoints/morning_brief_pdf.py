"""GET /api/ai/morning-brief/{brief_id}/pdf — PDF-экспорт брифинга."""
from __future__ import annotations

import io
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..cache import get_cache
from ..models import MorningBrief

logger = logging.getLogger("genomeai.ai.endpoint.morning_brief_pdf")
router = APIRouter()

_LOGO_PATH = Path(__file__).parents[4] / "web_cabinet" / "static" / "logo.png"
_BRAND_TEAL = (0, 150, 136)  # teal accent
_BRAND_DARK = (30, 30, 30)

_FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
_FONT_MONO = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


@router.get("/morning-brief/{brief_id}/pdf")
async def export_morning_brief_pdf(brief_id: str, farm_id: str = "demo-farm-v1") -> StreamingResponse:
    """Генерирует PDF-брифинг с брендингом GenomeAI."""
    brief = _load_brief(brief_id, farm_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"brief {brief_id!r} not found")
    pdf_bytes = _render_pdf(brief)
    filename = f"morning_brief_{brief.date}_{farm_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_brief(brief_id: str, farm_id: str) -> Optional[MorningBrief]:
    cache = get_cache()
    today_key = cache.make_key("morning_brief", {"farm_id": farm_id, "date": date.today().isoformat()})
    cached = cache.get(today_key)
    if cached:
        try:
            b = MorningBrief(**json.loads(cached))
            if b.brief_id == brief_id or brief_id == "today":
                return b
        except Exception:
            pass

    if brief_id == "today":
        cached2 = cache.get(today_key)
        if cached2:
            try:
                return MorningBrief(**json.loads(cached2))
            except Exception:
                pass

    from .morning_brief import _load_seeded_brief
    seeded = _load_seeded_brief(farm_id, date.today())
    return seeded


def _render_pdf(brief: MorningBrief) -> bytes:
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

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if _FONT_REGULAR.exists():
        pdfmetrics.registerFont(TTFont("DejaVu", str(_FONT_REGULAR)))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_FONT_BOLD)))
        pdfmetrics.registerFont(TTFont("DejaVu-Mono", str(_FONT_MONO)))
        _font = "DejaVu"
        _font_bold = "DejaVu-Bold"
    else:
        _font = "Helvetica"
        _font_bold = "Helvetica-Bold"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Утренний брифинг GenomeAI — {brief.date}",
    )

    styles = getSampleStyleSheet()
    teal = colors.Color(_BRAND_TEAL[0] / 255, _BRAND_TEAL[1] / 255, _BRAND_TEAL[2] / 255)
    dark = colors.Color(_BRAND_DARK[0] / 255, _BRAND_DARK[1] / 255, _BRAND_DARK[2] / 255)

    def style(name: str, bold: bool = False, **kw: object) -> ParagraphStyle:
        base = styles["Normal"].clone(name)
        base.fontName = _font_bold if bold else _font
        for k, v in kw.items():
            setattr(base, k, v)
        return base

    h1 = style("H1", bold=True, fontSize=20, textColor=teal, spaceAfter=4, leading=24)
    h2 = style("H2", bold=True, fontSize=14, textColor=dark, spaceAfter=2, leading=18)
    body = style("Body", fontSize=10, textColor=dark, spaceAfter=4, leading=14)
    caption = style("Caption", fontSize=8, textColor=colors.grey, spaceAfter=2)

    story = []

    # Header
    story.append(Paragraph("GenomeAI · ИИ-помощник", caption))
    story.append(Paragraph(f"Утренний брифинг {brief.date}", h1))
    story.append(Paragraph(f"Ферма: {brief.farm_id} · Сгенерирован: {brief.generated_at_utc.strftime('%H:%M UTC')}", caption))
    story.append(HRFlowable(width="100%", thickness=2, color=teal, spaceAfter=8))

    # Headline
    story.append(Paragraph(brief.headline, h2))
    story.append(Paragraph(brief.main_takeaway, body))
    story.append(Spacer(1, 0.4 * cm))

    # Overnight changes
    if brief.overnight_changes:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Что изменилось за ночь", h2))
        for ch in brief.overnight_changes:
            # Strip [evidence: ...] tags from display text
            import re as _re
            clean = _re.sub(r'\s*\[evidence:[^\]]*\]', '', ch.text).strip()
            story.append(Paragraph(f"• {clean}", body))
        story.append(Spacer(1, 0.3 * cm))

    # Today actions
    if brief.today_actions:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Требует внимания сегодня", h2))
        priority_color = {"high": colors.red, "medium": colors.orange, "low": colors.green}
        cell = style("Cell", fontSize=9, textColor=dark, leading=13)
        hdr = style("Hdr", bold=True, fontSize=9, textColor=colors.white, leading=13)
        table_data = [[
            Paragraph("Действие", hdr),
            Paragraph("Приоритет", hdr),
            Paragraph("До", hdr),
            Paragraph("Ответственный", hdr),
        ]]
        for act in brief.today_actions:
            table_data.append([
                Paragraph(act.action, cell),
                Paragraph(act.priority, cell),
                Paragraph(act.due or "—", cell),
                Paragraph(act.role, cell),
            ])
        tbl = Table(table_data, colWidths=[9 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), teal),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), _font_bold),
            ("FONTNAME", (0, 1), (-1, -1), _font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.96, 0.98, 0.98)]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.3 * cm))

    # Notes
    if brief.notes:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("На заметку", h2))
        for note in brief.notes:
            story.append(Paragraph(f"• {note}", body))
        story.append(Spacer(1, 0.3 * cm))

    # QR footer
    story.append(HRFlowable(width="100%", thickness=2, color=teal, spaceBefore=8))
    story.append(Spacer(1, 0.2 * cm))
    qr_img = _make_qr(brief)
    if qr_img:
        from reportlab.platypus import Image as RLImage
        story.append(RLImage(qr_img, width=2.5 * cm, height=2.5 * cm))

    doc.build(story)
    return buf.getvalue()


def _make_qr(brief: MorningBrief) -> Optional[io.BytesIO]:
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=3, border=1)
        qr.add_data(f"https://app.genomeai.ru/daily-summary?brief={brief.brief_id}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as exc:
        logger.warning(f"QR generation failed: {exc}")
        return None
