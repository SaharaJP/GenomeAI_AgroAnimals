"""POST /api/ai/weekly-brief — еженедельный брифинг фермы.
POST /api/ai/weekly-brief/pdf — PDF-экспорт брифинга (reportlab).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import get_ai_settings

logger = logging.getLogger("genomeai.ai.weekly_brief")
router = APIRouter()


# ── Request / Response schemas ───────────────────────────────────────────────

class WeeklyBriefRequest(BaseModel):
    week_start: str
    week_end: str
    farm_id: str = "demo-farm-v1"
    user_id: str = "anonymous"


class BriefKpis(BaseModel):
    avg_milk_yield_kg: float
    health_index_pct: float
    conceptions_confirmed: int
    calvings: int


class BriefRecommendation(BaseModel):
    text: str
    priority: str  # 'high' | 'medium' | 'low'


class WeeklyBriefResponse(BaseModel):
    brief_id: str
    week_start: str
    week_end: str
    farm_id: str
    kpis: BriefKpis
    summary: str
    narrative: list[str] = []
    key_events: list[str] = []
    recommendations: list[BriefRecommendation] = []
    demo_cached: bool = False
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WeeklyBriefPdfRequest(BaseModel):
    brief: dict


# ── Seeded demo data ─────────────────────────────────────────────────────────

_SEEDED_BRIEFS: list[dict] = [
    {
        "brief_id": "WBRIEF_20260421",
        "week_start": "2026-04-15",
        "week_end": "2026-04-21",
        "farm_id": "INV_FARM_001",
        "kpis": {
            "avg_milk_yield_kg": 28.4,
            "health_index_pct": 94,
            "conceptions_confirmed": 5,
            "calvings": 1,
        },
        "summary": "Стабильная неделя. Мастит у Ночки на контроле. PR 24% — рекорд фермы.",
        "narrative": [
            "Прошедшая неделя (15–21 апреля) отличалась высокой производственной стабильностью. "
            "Средний удой по стаду составил 28,4 кг, что на 0,3 кг выше целевого уровня. "
            "Индекс здоровья стада удерживается на отметке 94%, что свидетельствует об эффективном "
            "ветеринарном контроле.",
            "Основным ветеринарным событием недели стал клинический мастит у Ночки (корова #342, "
            "лактация 3). Случай зафиксирован во вторник, животное переведено на лечебный протокол. "
            "Карентный период по молоку — 5 дней. Остальные коровы в удовлетворительном состоянии.",
            "По направлению воспроизводства неделя выдалась результативной: подтверждено 5 стельностей "
            "по данным УЗИ, зафиксировано 1 отёл без осложнений. Показатель стельности (PR) достиг "
            "24% — рекордное значение для фермы за последние 3 месяца.",
            "Финансовая проекция недели: при сохранении текущих KPI плановая выручка от реализации "
            "молока составит 487 600 ₽, что на 2,1% выше прошлонедельного показателя.",
        ],
        "key_events": [
            "Мастит у Ночки (#342) — лечебный протокол, карентный период 5 дней",
            "Отёл Зорьки (#117) — тёлка 41 кг, без осложнений",
            "5 стельностей подтверждено УЗИ (коровы #201, #204, #212, #228, #315)",
            "Суточный удой >28 кг у 14 коров из 87 дойных",
        ],
        "recommendations": [
            {
                "text": "Усилить мониторинг Ночки (#342) — ежедневная термометрия и контроль SCC до окончания карентного периода",
                "priority": "high",
            },
            {
                "text": "Запланировать осеменение Зорьки (#117) через 60 дней после отёла (ориент. 20 июня)",
                "priority": "medium",
            },
            {
                "text": "Повторить УЗИ у коров с сомнительным результатом (#189, #233, #267) в течение недели",
                "priority": "medium",
            },
            {
                "text": "Проверить BCS у 6 коров с удоем ниже 20 кг/день — возможен энергодефицит",
                "priority": "low",
            },
            {
                "text": "Обновить план закупки кормовых добавок на май — текущего запаса осталось на 12 дней",
                "priority": "medium",
            },
        ],
        "demo_cached": True,
    },
    {
        "brief_id": "WBRIEF_20260414",
        "week_start": "2026-04-08",
        "week_end": "2026-04-14",
        "farm_id": "INV_FARM_001",
        "kpis": {
            "avg_milk_yield_kg": 29.1,
            "health_index_pct": 95,
            "conceptions_confirmed": 7,
            "calvings": 2,
        },
        "summary": "Высокая продуктивность. 2 отёла. Heat detection волна: 11 осеменений.",
        "narrative": [
            "Неделя с 8 по 14 апреля стала одной из лучших по продуктивности за квартал. "
            "Средний удой составил 29,1 кг — на 1,2 кг выше среднеквартального показателя. "
            "Индекс здоровья стада достиг 95%.",
            "Два успешных отёла: Майка (#089, телёнок-бычок 39 кг) и Росинка (#156, тёлка 42 кг). "
            "Оба отёла без осложнений, новотёлки переведены в секцию свежих коров.",
            "Волна охоты принесла 11 осеменений за 3 дня. Подтверждено 7 стельностей — рекордный "
            "еженедельный показатель. Программа синхронизации охоты работает эффективно.",
            "Потребление корма на уровне нормы, TMR-раздача без сбоев. Качество силоса по "
            "лабораторному анализу: сухое вещество 32%, НДК 42% — в рамках норматива.",
        ],
        "key_events": [
            "Отёл Майки (#089) — бычок 39 кг, без осложнений",
            "Отёл Росинки (#156) — тёлка 42 кг, без осложнений",
            "11 осеменений за 3 дня (волна охоты)",
            "7 стельностей подтверждено — рекорд недели",
        ],
        "recommendations": [
            {
                "text": "Начать контроль воспроизводительной функции Майки (#089) через 21 день после отёла",
                "priority": "medium",
            },
            {
                "text": "Зафиксировать дату осеменения для 11 осеменённых коров и внести в план контроля",
                "priority": "high",
            },
            {
                "text": "Запасы TMR на 18 дней — провести плановую закупку в течение следующей недели",
                "priority": "low",
            },
        ],
        "demo_cached": True,
    },
]


def _pick_seeded(week_start: str, week_end: str) -> dict:
    for b in _SEEDED_BRIEFS:
        if b["week_start"] == week_start or b["week_end"] == week_end:
            return b
    return _SEEDED_BRIEFS[0]


# ── PDF generation ────────────────────────────────────────────────────────────

_PALETTE = {
    "primary": "#17324D",
    "secondary": "#2E5B88",
    "accent_soft": "#DDF4EC",
    "accent_text": "#0F766E",
    "muted": "#66778A",
    "text": "#203041",
    "bg": "#F7F9FC",
    "border": "#D6DFEA",
    "white": "#FFFFFF",
    "danger_bg": "#FDE2E4",
    "danger_text": "#9F2A37",
    "warning_bg": "#FFF2D6",
    "warning_text": "#92400E",
}

_PRIORITY_COLORS = {
    "high": ("danger_bg", "danger_text", "Высокий"),
    "medium": ("warning_bg", "warning_text", "Средний"),
    "low": ("bg", "muted", "Низкий"),
}


def _build_brief_pdf(brief: dict) -> bytes:
    """Render branded PDF for a weekly brief using reportlab."""
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    def c(key: str) -> rl_colors.Color:
        return rl_colors.HexColor(_PALETTE[key])

    font = "Helvetica"
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                font = "DejaVuSans"
            except Exception:
                pass
            break

    buf = BytesIO()
    week_start = brief.get("week_start", "")
    week_end = brief.get("week_end", "")
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=f"Брифинг фермы {week_start} — {week_end}",
        author="GenomeAI AgroAnimals",
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    base = getSampleStyleSheet()
    body = ParagraphStyle("Br_body", parent=base["BodyText"], fontName=font, fontSize=9,
                          leading=13, textColor=c("text"), alignment=TA_LEFT)
    small = ParagraphStyle("Br_small", parent=body, fontSize=8, leading=11, textColor=c("muted"))
    white_lg = ParagraphStyle("Br_wlg", parent=base["Title"], fontName=font, fontSize=20,
                              leading=24, textColor=rl_colors.white)
    white_sm = ParagraphStyle("Br_wsm", parent=body, fontSize=10, leading=13,
                              textColor=rl_colors.white)
    h2 = ParagraphStyle("Br_h2", parent=base["Heading2"], fontName=font, fontSize=13,
                        leading=16, textColor=c("primary"), spaceBefore=8, spaceAfter=6)
    metric_val = ParagraphStyle("Br_mv", parent=base["Heading1"], fontName=font, fontSize=18,
                                leading=20, textColor=c("accent_text"))
    metric_lbl = ParagraphStyle("Br_ml", parent=small, fontSize=8, leading=10,
                                textColor=c("secondary"))

    story: list = []

    # ── Header hero ──────────────────────────────────────────────────────────
    farm_id = brief.get("farm_id", "")
    hero_left = [
        Paragraph("GenomeAI AgroAnimals", white_sm),
        Spacer(1, 4),
        Paragraph("Брифинг фермы", white_lg),
        Spacer(1, 4),
        Paragraph(f"{week_start} — {week_end}", white_sm),
    ]
    hero_right = [
        Paragraph("GAI", white_lg),
        Spacer(1, 6),
        Paragraph(f"<b>Ферма</b><br/>{farm_id}", white_sm),
    ]
    hero = Table([[hero_left, hero_right]], colWidths=[120 * mm, 58 * mm])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c("primary")),
        ("BACKGROUND", (1, 0), (1, 0), c("secondary")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(hero)
    story.append(Spacer(1, 10))

    # ── Summary banner ───────────────────────────────────────────────────────
    summary = brief.get("summary", "")
    if summary:
        box = Table([[Paragraph(summary, body)]], colWidths=[178 * mm])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c("accent_soft")),
            ("BOX", (0, 0), (-1, -1), 0.8, c("border")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(box)
        story.append(Spacer(1, 10))

    # ── KPI cards ────────────────────────────────────────────────────────────
    kpis = brief.get("kpis", {})
    kpi_items = [
        (f"{kpis.get('avg_milk_yield_kg', 0)} кг", "Средний удой"),
        (f"{kpis.get('health_index_pct', 0)}%", "Индекс здоровья"),
        (str(kpis.get("conceptions_confirmed", 0)), "Стельностей"),
        (str(kpis.get("calvings", 0)), "Отёлов"),
    ]
    kpi_cells = []
    for val, lbl in kpi_items:
        card = Table(
            [[Paragraph(val, metric_val)], [Paragraph(lbl, metric_lbl)]],
            colWidths=[42 * mm],
        )
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c("bg")),
            ("BOX", (0, 0), (-1, -1), 0.7, c("border")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        kpi_cells.append(card)
    kpi_row = Table([kpi_cells], colWidths=[44 * mm, 44 * mm, 44 * mm, 44 * mm])
    kpi_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(kpi_row)
    story.append(Spacer(1, 12))

    # ── Narrative ────────────────────────────────────────────────────────────
    narrative = brief.get("narrative", [])
    if narrative:
        story.append(Paragraph("Анализ недели", h2))
        for para in narrative:
            story.append(Paragraph(para, body))
            story.append(Spacer(1, 6))

    # ── Key events ───────────────────────────────────────────────────────────
    key_events = brief.get("key_events", [])
    if key_events:
        story.append(Paragraph("Ключевые события", h2))
        for ev in key_events:
            story.append(Paragraph(f"• {ev}", body))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 4))

    # ── Recommendations ──────────────────────────────────────────────────────
    recs = brief.get("recommendations", [])
    if recs:
        story.append(Paragraph("Рекомендации", h2))
        for rec in recs:
            if isinstance(rec, dict):
                priority = rec.get("priority", "low")
                text = rec.get("text", "")
            else:
                priority = "low"
                text = str(rec)
            bg_key, txt_key, label = _PRIORITY_COLORS.get(priority, _PRIORITY_COLORS["low"])
            chip_style = ParagraphStyle(
                f"chip_{priority}", parent=small, fontSize=7, textColor=c(txt_key),
            )
            chip = Table([[Paragraph(label, chip_style)]], colWidths=[18 * mm])
            chip.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), c(bg_key)),
                ("BOX", (0, 0), (-1, -1), 0.5, c("border")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            row = Table([[chip, Paragraph(text, body)]], colWidths=[22 * mm, 154 * mm])
            row.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), c("bg")),
                ("BOX", (0, 0), (-1, -1), 0.7, c("border")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(row)
            story.append(Spacer(1, 5))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Сгенерировано GenomeAI AgroAnimals · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        small,
    ))

    doc.build(story)
    return buf.getvalue()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/weekly-brief", response_model=WeeklyBriefResponse)
async def generate_weekly_brief(body: WeeklyBriefRequest) -> WeeklyBriefResponse:
    """POST /api/ai/weekly-brief — возвращает еженедельный брифинг фермы."""
    settings = get_ai_settings()

    if settings.GENOMEAI_AI_DEMO_MODE or not settings.is_configured:
        seeded = _pick_seeded(body.week_start, body.week_end)
        logger.info(json.dumps({
            "event": "weekly_brief_demo",
            "brief_id": seeded["brief_id"],
            "week_start": body.week_start,
            "week_end": body.week_end,
        }))
        return WeeklyBriefResponse(
            **{k: v for k, v in seeded.items() if k != "generated_at"},
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # Live mode — delegate to Claude (same pattern as ask_farm)
    try:
        from ..client import get_client
        from ..context import build_demo_farm_context
        from ..prompts.weekly_brief import WEEKLY_BRIEF_SYSTEM, build_weekly_brief_message

        ctx = build_demo_farm_context()
        user_message = build_weekly_brief_message(ctx, body.week_start, body.week_end)
        client = get_client()
        full_text = ""
        async for chunk in client.astream(
            user_message=user_message,
            system_prompt=WEEKLY_BRIEF_SYSTEM,
            farm_context=ctx.to_text(),
            task_type="weekly_brief",
            user_id=body.user_id,
        ):
            full_text += chunk

        import re
        json_match = re.search(r"\{.*\}", full_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            exec_summary = parsed.get("executive_summary", "")
            recs = [
                BriefRecommendation(text=r, priority="medium")
                for r in parsed.get("recommendations", [])
            ]
            return WeeklyBriefResponse(
                brief_id=f"WBRIEF_{body.week_end.replace('-', '')}",
                week_start=body.week_start,
                week_end=body.week_end,
                farm_id=body.farm_id,
                kpis=BriefKpis(
                    avg_milk_yield_kg=0,
                    health_index_pct=0,
                    conceptions_confirmed=0,
                    calvings=0,
                ),
                summary=exec_summary[:300] if exec_summary else "",
                narrative=[exec_summary] if exec_summary else [],
                key_events=[],
                recommendations=recs,
                demo_cached=False,
            )
    except Exception as exc:
        logger.error(f"weekly_brief live error: {exc}")

    # Graceful fallback to seeded
    seeded = _pick_seeded(body.week_start, body.week_end)
    return WeeklyBriefResponse(
        **{k: v for k, v in seeded.items() if k != "generated_at"},
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/weekly-brief/pdf")
async def export_weekly_brief_pdf(body: WeeklyBriefPdfRequest) -> Response:
    """POST /api/ai/weekly-brief/pdf — генерирует PDF брифинга через reportlab."""
    try:
        pdf_bytes = _build_brief_pdf(body.brief)
    except Exception as exc:
        logger.error(f"weekly_brief_pdf error: {exc}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    brief_id = body.brief.get("brief_id", "briefing")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="briefing-{brief_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )
