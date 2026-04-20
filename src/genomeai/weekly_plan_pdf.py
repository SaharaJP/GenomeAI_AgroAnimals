from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from pypdf import PdfReader

from .versioning import write_checksums, write_json


DEFAULT_WEEKLY_PLAN_PDF_CFG: Dict[str, Any] = {
    "weekly_plan_pdf_v1": {
        "theme_name": "genomeai_weekly_plan_v1",
        "brand_name": "GenomeAI AgroAnimals",
        "brand_tagline": "Weekly Action Plan - fact-based planning for dairy operations",
        "logo_label": "GAI",
        "charts": {
            "max_domains": 6,
            "max_source_runs": 6,
            "max_teams": 6,
        },
        "palette": {
            "primary": "#17324D",
            "secondary": "#2E5B88",
            "accent": "#2AA876",
            "accent_soft": "#DDF4EC",
            "info": "#DCEAF7",
            "warning": "#FFF2D6",
            "danger": "#FDE2E4",
            "neutral": "#F7F9FC",
            "border": "#D6DFEA",
            "text": "#203041",
            "muted": "#66778A",
            "white": "#FFFFFF",
            "chart_1": "#2E5B88",
            "chart_2": "#2AA876",
            "chart_3": "#F0A202",
            "chart_4": "#5C6BC0",
            "chart_5": "#D96C75",
            "chart_6": "#7BC4C4",
        },
    }
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(dst)
    for key, value in (src or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(dict(out[key]), value)
        else:
            out[key] = value
    return out


def _load_weekly_plan_pdf_cfg(cfg_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(cfg_path) if cfg_path is not None else (_project_root() / "configs" / "reports" / "weekly_plan_pdf_v1.yaml")
    merged = dict(DEFAULT_WEEKLY_PLAN_PDF_CFG)
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if isinstance(loaded, dict):
            merged = _deep_merge(merged, loaded)
    return merged


def _register_fonts() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                return "DejaVuSans"
            except Exception:
                continue
    return "Helvetica"


def _clean(value: Any) -> str:
    if value in (None, ""):
        return "NA"
    return str(value)


def _truncate(value: Any, limit: int = 220) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _hex(theme: Dict[str, Any], key: str, fallback: str) -> colors.Color:
    palette = theme.get("palette") or {}
    return colors.HexColor(str(palette.get(key) or fallback))


def _chart_palette(theme: Dict[str, Any]) -> List[colors.Color]:
    return [
        _hex(theme, "chart_1", "#2E5B88"),
        _hex(theme, "chart_2", "#2AA876"),
        _hex(theme, "chart_3", "#F0A202"),
        _hex(theme, "chart_4", "#5C6BC0"),
        _hex(theme, "chart_5", "#D96C75"),
        _hex(theme, "chart_6", "#7BC4C4"),
    ]


def _collect_action_citations(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in list(plan.get("action_items") or []):
        if not isinstance(item, dict):
            continue
        for cit in list(item.get("citations") or []):
            if isinstance(cit, dict):
                out.append(dict(cit))
    return out


def _collect_source_run_ids(plan: Dict[str, Any]) -> List[str]:
    run_ids = {str(x) for x in (plan.get("source_run_ids") or []) if str(x).strip()}
    for item in list(plan.get("action_items") or []):
        if not isinstance(item, dict):
            continue
        for rid in list(item.get("source_run_ids") or []):
            if str(rid).strip():
                run_ids.add(str(rid))
        for cit in list(item.get("citations") or []):
            if isinstance(cit, dict) and str(cit.get("run_id") or "").strip():
                run_ids.add(str(cit.get("run_id")))
    return sorted(run_ids)


def _collect_unique_citations(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for cit in list(plan.get("citations") or []) + _collect_action_citations(plan):
        if not isinstance(cit, dict):
            continue
        key = str(cit.get("target") or cit.get("fact_id") or id(cit))
        if key in seen:
            continue
        seen.add(key)
        unique.append(cit)
    return unique


def _citation_line(cit: Dict[str, Any]) -> str:
    return (
        f"section={_clean(cit.get('section'))}; "
        f"table={_clean(cit.get('table'))}; "
        f"metric={_clean(cit.get('metric'))}; "
        f"run_id={_clean(cit.get('run_id'))}; "
        f"fact_id={_clean(cit.get('fact_id'))}"
    )


def _build_styles(font_name: str, theme: Dict[str, Any]) -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    primary = _hex(theme, "primary", "#17324D")
    secondary = _hex(theme, "secondary", "#2E5B88")
    text = _hex(theme, "text", "#203041")
    muted = _hex(theme, "muted", "#66778A")
    body = ParagraphStyle(
        "WeeklyPlanBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
        textColor=text,
        spaceAfter=2,
    )
    small = ParagraphStyle(
        "WeeklyPlanSmall",
        parent=body,
        fontSize=8,
        leading=10,
        textColor=muted,
    )
    heading = ParagraphStyle(
        "WeeklyPlanHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13,
        leading=16,
        textColor=primary,
        spaceAfter=6,
        spaceBefore=8,
    )
    section_lead = ParagraphStyle(
        "WeeklyPlanSectionLead",
        parent=body,
        fontSize=9,
        leading=12,
        textColor=muted,
        spaceAfter=6,
    )
    title = ParagraphStyle(
        "WeeklyPlanTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=26,
        textColor=_hex(theme, "white", "#FFFFFF"),
        spaceAfter=6,
    )
    subtitle = ParagraphStyle(
        "WeeklyPlanSubtitle",
        parent=body,
        fontSize=10,
        leading=13,
        textColor=_hex(theme, "info", "#DCEAF7"),
    )
    metric_value = ParagraphStyle(
        "WeeklyPlanMetricValue",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=18,
        leading=20,
        textColor=primary,
        spaceAfter=2,
    )
    metric_label = ParagraphStyle(
        "WeeklyPlanMetricLabel",
        parent=small,
        fontSize=8,
        leading=10,
        textColor=secondary,
    )
    card_title = ParagraphStyle(
        "WeeklyPlanCardTitle",
        parent=heading,
        fontSize=11,
        leading=14,
        textColor=primary,
        spaceAfter=4,
        spaceBefore=0,
    )
    card_meta = ParagraphStyle(
        "WeeklyPlanCardMeta",
        parent=small,
        fontSize=8,
        leading=10,
        textColor=secondary,
    )
    footer = ParagraphStyle(
        "WeeklyPlanFooter",
        parent=small,
        fontSize=7,
        leading=8,
        textColor=muted,
    )
    chip = ParagraphStyle(
        "WeeklyPlanChip",
        parent=small,
        fontSize=7,
        leading=8,
        textColor=_hex(theme, "white", "#FFFFFF"),
        alignment=TA_LEFT,
    )
    return {
        "title": title,
        "subtitle": subtitle,
        "heading": heading,
        "section_lead": section_lead,
        "body": body,
        "small": small,
        "metric_value": metric_value,
        "metric_label": metric_label,
        "card_title": card_title,
        "card_meta": card_meta,
        "footer": footer,
        "chip": chip,
    }


def _status_chip_color(status: str, theme: Dict[str, Any]) -> colors.Color:
    mapping = {
        "draft": _hex(theme, "warning", "#FFF2D6"),
        "approved": _hex(theme, "accent_soft", "#DDF4EC"),
        "archived": _hex(theme, "neutral", "#F7F9FC"),
        "rejected": _hex(theme, "danger", "#FDE2E4"),
    }
    return mapping.get(str(status or "draft").lower(), _hex(theme, "warning", "#FFF2D6"))


def _status_text_color(status: str, theme: Dict[str, Any]) -> colors.Color:
    mapping = {
        "draft": _hex(theme, "primary", "#17324D"),
        "approved": _hex(theme, "accent", "#2AA876"),
        "archived": _hex(theme, "muted", "#66778A"),
        "rejected": colors.HexColor("#9F2A37"),
    }
    return mapping.get(str(status or "draft").lower(), _hex(theme, "primary", "#17324D"))


def _safe_counter(items: Iterable[str], *, limit: int = 6) -> Counter[str]:
    c = Counter(str(x) for x in items if str(x).strip())
    return Counter(dict(c.most_common(limit)))


def _plan_stats(plan: Dict[str, Any], theme: Dict[str, Any]) -> Dict[str, Any]:
    action_items = [dict(x or {}) for x in list(plan.get("action_items") or []) if isinstance(x, dict)]
    unique_citations = _collect_unique_citations(plan)
    run_ids = _collect_source_run_ids(plan)
    domains = _safe_counter([str(x.get("domain") or "data") for x in action_items], limit=int((((theme.get("charts") or {}).get("max_domains")) or 6)))
    priorities = _safe_counter([f"P{_clean(x.get('priority'))}" for x in action_items], limit=6)
    teams = _safe_counter([str(x.get("assignee_team") or "unassigned") for x in action_items], limit=int((((theme.get("charts") or {}).get("max_teams")) or 6)))
    source_sections = _safe_counter([str(c.get("section") or "NA") for c in unique_citations], limit=6)
    source_runs = _safe_counter(run_ids, limit=int((((theme.get("charts") or {}).get("max_source_runs")) or 6)))
    high_priority = sum(1 for x in action_items if str(x.get("priority") or "") in {"1", "2"})
    return {
        "item_count": len(action_items),
        "citation_count": len(unique_citations),
        "run_count": len(run_ids),
        "team_count": len(teams),
        "high_priority_count": high_priority,
        "domains": domains,
        "priorities": priorities,
        "teams": teams,
        "source_sections": source_sections,
        "source_runs": source_runs,
    }


def _hero_block(plan: Dict[str, Any], styles: Dict[str, ParagraphStyle], theme: Dict[str, Any]) -> Table:
    brand_name = _clean((theme.get("brand_name") or "GenomeAI AgroAnimals"))
    brand_tagline = _clean((theme.get("brand_tagline") or "Weekly Action Plan"))
    logo_label = _clean((theme.get("logo_label") or "GAI"))
    title = _clean(plan.get("name") or f"Weekly Plan {_clean(plan.get('plan_id'))}")
    status = _clean(plan.get("status") or "draft")
    week_start = _clean(plan.get("week_start"))
    farm_id = _clean(plan.get("farm_id"))
    meta_html = (
        f"<b>Status</b><br/>{status}<br/><br/>"
        f"<b>Week start</b><br/>{week_start}<br/><br/>"
        f"<b>Farm</b><br/>{farm_id}<br/><br/>"
        f"<b>Data version</b><br/>{_clean(plan.get('data_version'))}"
    )
    left = [
        Paragraph(f"<b>{brand_name}</b>", styles["subtitle"]),
        Spacer(1, 2),
        Paragraph(title, styles["title"]),
        Spacer(1, 4),
        Paragraph(brand_tagline, styles["subtitle"]),
    ]
    right = [
        Paragraph(f"<b>{logo_label}</b>", styles["title"]),
        Spacer(1, 4),
        Paragraph(meta_html, styles["subtitle"]),
    ]
    table = Table([[left, right]], colWidths=[120 * mm, 58 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _hex(theme, "primary", "#17324D")),
                ("BOX", (0, 0), (-1, -1), 0, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("BACKGROUND", (1, 0), (1, 0), _hex(theme, "secondary", "#2E5B88")),
            ]
        )
    )
    return table


def _metric_card(value: str, label: str, styles: Dict[str, ParagraphStyle], theme: Dict[str, Any]) -> Table:
    card = Table(
        [[Paragraph(str(value), styles["metric_value"])], [Paragraph(label, styles["metric_label"])]],
        colWidths=[42 * mm],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _hex(theme, "neutral", "#F7F9FC")),
                ("BOX", (0, 0), (-1, -1), 0.7, _hex(theme, "border", "#D6DFEA")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return card


def _summary_cards(plan: Dict[str, Any], styles: Dict[str, ParagraphStyle], theme: Dict[str, Any], stats: Dict[str, Any]) -> Table:
    cards = [
        _metric_card(str(stats["item_count"]), "Пунктов в weekly plan", styles, theme),
        _metric_card(str(stats["citation_count"]), "Уникальных ссылок на факты", styles, theme),
        _metric_card(str(stats["run_count"]), "Source run_id в плане", styles, theme),
        _metric_card(str(stats["high_priority_count"]), "Пункты P1-P2", styles, theme),
    ]
    wrapper = Table([cards], colWidths=[44 * mm, 44 * mm, 44 * mm, 44 * mm])
    wrapper.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return wrapper


def _highlights_block(plan: Dict[str, Any], styles: Dict[str, ParagraphStyle], theme: Dict[str, Any]) -> Table:
    items = [dict(x or {}) for x in list(plan.get("action_items") or [])[:3] if isinstance(x, dict)]
    cells: List[Any] = []
    for idx, item in enumerate(items, start=1):
        domain = _clean(item.get("domain") or "data")
        priority = _clean(item.get("priority"))
        what_to_do = "<br/>".join(f"- {_truncate(step, 90)}" for step in list(item.get("what_to_do") or [])[:2])
        text = (
            f"<b>{idx}. {_truncate(item.get('title'), 70)}</b><br/>"
            f"<font color='#66778A'>domain={domain}; priority={priority}; team={_clean(item.get('assignee_team'))}</font><br/><br/>"
            f"{_truncate(item.get('expected_effect'), 150)}"
        )
        if what_to_do:
            text += f"<br/><br/>{what_to_do}"
        box = Table([[Paragraph(text, styles["body"])]], colWidths=[56 * mm])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _hex(theme, "white", "#FFFFFF")),
                    ("BOX", (0, 0), (-1, -1), 0.8, _hex(theme, "border", "#D6DFEA")),
                    ("LINEBEFORE", (0, 0), (0, -1), 4, _hex(theme, "accent", "#2AA876")),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        cells.append(box)
    while len(cells) < 3:
        cells.append(Spacer(1, 1))
    tbl = Table([cells], colWidths=[58 * mm, 58 * mm, 58 * mm])
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return tbl


def _bar_chart(*, title: str, labels: List[str], values: List[float], theme: Dict[str, Any], horizontal: bool = False, width: float = 250, height: float = 170) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, rx=10, ry=10, fillColor=_hex(theme, "white", "#FFFFFF"), strokeColor=_hex(theme, "border", "#D6DFEA"), strokeWidth=0.8))
    drawing.add(String(12, height - 18, title, fontName="Helvetica-Bold", fontSize=10, fillColor=_hex(theme, "primary", "#17324D")))
    palette = _chart_palette(theme)

    if horizontal:
        chart = HorizontalBarChart()
        chart.x = 58
        chart.y = 28
        chart.width = width - 76
        chart.height = height - 56
        chart.data = [values or [0.0]]
        chart.categoryAxis.categoryNames = labels or ["NA"]
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 7
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(max(values or [1.0]), 1.0) * 1.15
        chart.valueAxis.valueStep = max(1.0, round(chart.valueAxis.valueMax / 4))
        chart.bars[0].fillColor = palette[0]
        chart.bars[0].strokeColor = palette[0]
    else:
        chart = VerticalBarChart()
        chart.x = 30
        chart.y = 28
        chart.width = width - 48
        chart.height = height - 56
        chart.data = [values or [0.0]]
        chart.categoryAxis.categoryNames = labels or ["NA"]
        chart.categoryAxis.labels.fontSize = 7
        chart.categoryAxis.labels.angle = 0
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(max(values or [1.0]), 1.0) * 1.15
        chart.valueAxis.valueStep = max(1.0, round(chart.valueAxis.valueMax / 4))
        chart.bars[0].fillColor = palette[1]
        chart.bars[0].strokeColor = palette[1]
    chart.strokeColor = _hex(theme, "border", "#D6DFEA")
    chart.valueAxis.strokeColor = _hex(theme, "border", "#D6DFEA")
    chart.categoryAxis.strokeColor = _hex(theme, "border", "#D6DFEA")
    drawing.add(chart)
    return drawing


def _pie_chart(*, title: str, labels: List[str], values: List[float], theme: Dict[str, Any], width: float = 250, height: float = 170) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, rx=10, ry=10, fillColor=_hex(theme, "white", "#FFFFFF"), strokeColor=_hex(theme, "border", "#D6DFEA"), strokeWidth=0.8))
    drawing.add(String(12, height - 18, title, fontName="Helvetica-Bold", fontSize=10, fillColor=_hex(theme, "primary", "#17324D")))
    pie = Pie()
    pie.x = 18
    pie.y = 12
    pie.width = 104
    pie.height = 104
    pie.sideLabels = True
    pie.simpleLabels = False
    pie.labels = [f"{_truncate(lbl, 16)} ({int(val)})" for lbl, val in zip(labels or ["NA"], values or [1.0])]
    pie.data = values or [1.0]
    pie.slices.strokeWidth = 0.5
    palette = _chart_palette(theme)
    for idx in range(len(pie.data)):
        pie.slices[idx].fillColor = palette[idx % len(palette)]
        pie.slices[idx].strokeColor = colors.white
    drawing.add(pie)
    legend_y = height - 40
    for idx, lbl in enumerate(labels[:5]):
        color = palette[idx % len(palette)]
        drawing.add(Rect(140, legend_y - idx * 18, 8, 8, fillColor=color, strokeColor=color))
        drawing.add(String(154, legend_y - idx * 18 + 1, _truncate(lbl, 24), fontName="Helvetica", fontSize=7, fillColor=_hex(theme, "text", "#203041")))
    return drawing


def _chart_blocks(plan: Dict[str, Any], theme: Dict[str, Any], stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    priorities = stats.get("priorities") or Counter()
    if priorities:
        labels = list(priorities.keys())
        values = [float(v) for v in priorities.values()]
        blocks.append({
            "key": "priority_distribution",
            "title": "Распределение пунктов по приоритетам",
            "drawing": _bar_chart(title="Распределение пунктов по приоритетам", labels=labels, values=values, theme=theme, horizontal=False),
        })
    domains = stats.get("domains") or Counter()
    if domains:
        labels = list(domains.keys())
        values = [float(v) for v in domains.values()]
        blocks.append({
            "key": "domain_distribution",
            "title": "Структура weekly plan по доменам",
            "drawing": _pie_chart(title="Структура weekly plan по доменам", labels=labels, values=values, theme=theme),
        })
    source_runs = stats.get("source_runs") or Counter()
    if source_runs:
        labels = list(source_runs.keys())
        values = [float(v) for v in source_runs.values()]
        blocks.append({
            "key": "source_runs",
            "title": "Покрытие source run_id в плане",
            "drawing": _bar_chart(title="Покрытие source run_id в плане", labels=labels, values=values, theme=theme, horizontal=True, width=520, height=180),
        })
    teams = stats.get("teams") or Counter()
    if teams and len(blocks) < 3:
        labels = list(teams.keys())
        values = [float(v) for v in teams.values()]
        blocks.append({
            "key": "assignee_teams",
            "title": "Распределение по командам-исполнителям",
            "drawing": _bar_chart(title="Распределение по командам-исполнителям", labels=labels, values=values, theme=theme, horizontal=True, width=520, height=180),
        })
    return blocks


def _action_card(item: Dict[str, Any], idx: int, styles: Dict[str, ParagraphStyle], theme: Dict[str, Any]) -> Table:
    citations = list(item.get("citations") or [])
    citation_lines = [f"- {_truncate(_citation_line(c), 210)}" for c in citations[:2]] or ["- Источник не указан"]
    steps = list(item.get("what_to_do") or [])
    steps_text = "<br/>".join(f"- {_truncate(step, 140)}" for step in steps[:3]) or "- Шаги не указаны"
    domain = _clean(item.get("domain") or "data")
    priority = _clean(item.get("priority"))
    assignee = _clean(item.get("assignee_team"))
    object_ref = f"{_clean(item.get('object_type'))}:{_clean(item.get('object_id'))}"
    why = item.get("why") or {}
    preview = why.get("row_preview") or {}
    preview_pairs = []
    if isinstance(preview, dict):
        for key in list(preview.keys())[:4]:
            preview_pairs.append(f"{_truncate(key, 16)}={_truncate(preview.get(key), 24)}")
    preview_text = "; ".join(preview_pairs) or "NA"
    header_html = (
        f"<b>{idx}. {_truncate(item.get('title'), 110)}</b><br/>"
        f"<font color='#2E5B88'>domain={domain}; priority={priority}; team={assignee}; object={object_ref}</font>"
    )
    body = [
        Paragraph(header_html, styles["card_title"]),
        Paragraph(f"<b>Ожидаемый эффект.</b> {_truncate(item.get('expected_effect'), 320)}", styles["body"]),
        Spacer(1, 2),
        Paragraph(f"<b>Что сделать на неделе.</b><br/>{steps_text}", styles["body"]),
        Spacer(1, 2),
        Paragraph(f"<b>Подтверждающий preview.</b> {_truncate(preview_text, 220)}", styles["small"]),
        Spacer(1, 2),
        Paragraph(f"<b>Источники.</b><br/>{'<br/>'.join(citation_lines)}", styles["small"]),
    ]
    card = Table([[body]], colWidths=[178 * mm])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _hex(theme, "white", "#FFFFFF")),
                ("BOX", (0, 0), (-1, -1), 0.8, _hex(theme, "border", "#D6DFEA")),
                ("LINEBEFORE", (0, 0), (0, -1), 4, _hex(theme, "secondary", "#2E5B88")),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return card


def _sources_table(plan: Dict[str, Any], styles: Dict[str, ParagraphStyle], theme: Dict[str, Any]) -> Table:
    rows: List[List[Any]] = [[
        Paragraph("<b>Раздел</b>", styles["body"]),
        Paragraph("<b>Таблица / metric</b>", styles["body"]),
        Paragraph("<b>run_id</b>", styles["body"]),
        Paragraph("<b>fact_id</b>", styles["body"]),
    ]]
    for cit in _collect_unique_citations(plan)[:12]:
        rows.append([
            Paragraph(_truncate(cit.get("section"), 44), styles["small"]),
            Paragraph(_truncate(f"{_clean(cit.get('table'))} / {_clean(cit.get('metric'))}", 38), styles["small"]),
            Paragraph(_truncate(cit.get("run_id"), 24), styles["small"]),
            Paragraph(_truncate(cit.get("fact_id"), 28), styles["small"]),
        ])
    tbl = Table(rows, colWidths=[56 * mm, 52 * mm, 28 * mm, 42 * mm], repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _hex(theme, "info", "#DCEAF7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), _hex(theme, "primary", "#17324D")),
                ("GRID", (0, 0), (-1, -1), 0.35, _hex(theme, "border", "#D6DFEA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _hex(theme, "neutral", "#F7F9FC")]),
            ]
        )
    )
    return tbl


def _missing_data_block(plan: Dict[str, Any], styles: Dict[str, ParagraphStyle], theme: Dict[str, Any]) -> Optional[Table]:
    missing = list(plan.get("missing_data_requests") or [])
    if not missing:
        return None
    rows = []
    for req in missing[:4]:
        needed = "; ".join(_truncate(x, 60) for x in list(req.get("needed_data") or [])[:3])
        how = "; ".join(_truncate(x, 60) for x in list(req.get("how_to_get") or [])[:3])
        html = f"<b>{_clean(req.get('section'))}</b><br/>{_truncate(req.get('why'), 180)}"
        if needed:
            html += f"<br/><b>Нужны данные:</b> {needed}"
        if how:
            html += f"<br/><b>Как получить:</b> {how}"
        rows.append([Paragraph(html, styles["small"])])
    tbl = Table(rows, colWidths=[178 * mm])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _hex(theme, "warning", "#FFF2D6")),
                ("BOX", (0, 0), (-1, -1), 0.8, _hex(theme, "border", "#D6DFEA")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return tbl


def _draw_page_chrome(canvas, doc, *, theme: Dict[str, Any]) -> None:
    page_w, page_h = A4
    primary = _hex(theme, "primary", "#17324D")
    secondary = _hex(theme, "secondary", "#2E5B88")
    muted = _hex(theme, "muted", "#66778A")
    brand_name = _clean(theme.get("brand_name") or "GenomeAI AgroAnimals")

    canvas.saveState()
    canvas.setFillColor(primary)
    canvas.rect(doc.leftMargin, page_h - 8 * mm, page_w - doc.leftMargin - doc.rightMargin, 1.4 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(_hex(theme, "border", "#D6DFEA"))
    canvas.line(doc.leftMargin, 10 * mm, page_w - doc.rightMargin, 10 * mm)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.setFillColor(secondary)
    canvas.drawString(doc.leftMargin, 6.5 * mm, brand_name)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(muted)
    canvas.drawRightString(page_w - doc.rightMargin, 6.5 * mm, f"Стр. {canvas.getPageNumber()}")
    canvas.restoreState()


def generate_weekly_plan_pdf(*, artifacts_root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Render weekly plan PDF into artifacts/<dv>/weekly_plans/<plan_id>/.

    The PDF remains deterministic with respect to the supplied plan payload and does not
    compute new domain metrics. It only formats the already stored weekly-plan facts,
    citations and action items into a branded, chart-based management report.
    """

    data_version = str(plan.get("data_version") or "NA")
    plan_id = str(plan.get("plan_id") or "").strip()
    if not plan_id:
        raise ValueError("weekly_plan.plan_id пуст: PDF export невозможен")

    cfg = _load_weekly_plan_pdf_cfg().get("weekly_plan_pdf_v1") or {}
    run_root = Path(artifacts_root) / data_version / "weekly_plans" / plan_id
    run_root.mkdir(parents=True, exist_ok=True)
    pdf_path = run_root / "weekly_plan.pdf"
    meta_path = run_root / "report_meta.json"

    font_name = _register_fonts()
    styles = _build_styles(font_name, cfg)
    stats = _plan_stats(plan, cfg)
    chart_blocks = _chart_blocks(plan, cfg, stats)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        title=str(plan.get("name") or f"Weekly Plan {plan_id}"),
        author=str(cfg.get("brand_name") or "GenomeAI AgroAnimals"),
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    story: List[Any] = []
    story.append(_hero_block(plan, styles, cfg))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Управленческая сводка", styles["heading"]))
    story.append(Paragraph("PDF собран только из уже сохранённого weekly plan и связанных citations. Новые вычисления поверх доменных данных не выполнялись.", styles["section_lead"]))
    story.append(_summary_cards(plan, styles, cfg, stats))
    story.append(Spacer(1, 8))

    summary = str(plan.get("summary") or "").strip()
    if summary:
        summary_box = Table([[Paragraph(summary.replace("\n", "<br/>"), styles["body"])]], colWidths=[178 * mm])
        summary_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _hex(cfg, "accent_soft", "#DDF4EC")),
                    ("BOX", (0, 0), (-1, -1), 0.8, _hex(cfg, "border", "#D6DFEA")),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        story.append(summary_box)
        story.append(Spacer(1, 8))

    story.append(Paragraph("Ключевые действия недели", styles["heading"]))
    story.append(_highlights_block(plan, styles, cfg))
    story.append(Spacer(1, 8))

    if chart_blocks:
        story.append(Paragraph("Графики недели", styles["heading"]))
        story.append(Paragraph("Графики показывают структуру плана по приоритетам, доменам и подтверждающим source run_id. Все данные на диаграммах получены из сохранённых action_items и citations weekly plan.", styles["section_lead"]))
        first_row = [block["drawing"] for block in chart_blocks[:2]]
        while len(first_row) < 2:
            first_row.append(Spacer(1, 1))
        charts_tbl = Table([first_row], colWidths=[89 * mm, 89 * mm])
        charts_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(charts_tbl)
        if len(chart_blocks) > 2:
            story.append(Spacer(1, 6))
            story.append(chart_blocks[2]["drawing"])
        story.append(PageBreak())

    story.append(Paragraph("План действий по пунктам", styles["heading"]))
    story.append(Paragraph("Ниже - детальные action cards с ожидаемым эффектом, следующими шагами и обязательными ссылками на источники fact-pack.", styles["section_lead"]))
    for idx, item in enumerate(list(plan.get("action_items") or []), start=1):
        story.append(_action_card(dict(item or {}), idx, styles, cfg))
        story.append(Spacer(1, 5))

    story.append(Spacer(1, 4))
    story.append(Paragraph("Реестр источников", styles["heading"]))
    story.append(_sources_table(plan, styles, cfg))

    missing_block = _missing_data_block(plan, styles, cfg)
    if missing_block is not None:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Нехватка данных", styles["heading"]))
        story.append(missing_block)

    doc.build(
        story,
        onFirstPage=lambda canv, document: _draw_page_chrome(canv, document, theme=cfg),
        onLaterPages=lambda canv, document: _draw_page_chrome(canv, document, theme=cfg),
    )

    page_count = 0
    try:
        page_count = len(PdfReader(str(pdf_path)).pages)
    except Exception:
        page_count = 0

    action_items = list(plan.get("action_items") or [])
    action_citations = _collect_action_citations(plan)
    meta = {
        "schema": "genomeai.weekly_plan.report_meta.v2",
        "generated_at_utc": _utc_now_iso(),
        "data_version": data_version,
        "plan_id": plan_id,
        "pdf_rel_path": str(pdf_path.relative_to(Path(artifacts_root))),
        "item_count": len(action_items),
        "citation_count": len(action_citations),
        "status": str(plan.get("status") or "draft"),
        "week_start": str(plan.get("week_start") or ""),
        "farm_id": plan.get("farm_id"),
        "approval_requested_by_username": plan.get("approval_requested_by_username"),
        "approved_by_username": plan.get("approved_by_username"),
        "tasks_created_run_id": plan.get("tasks_created_run_id"),
        "source_run_ids": _collect_source_run_ids(plan),
        "branding_theme": str(cfg.get("theme_name") or "genomeai_weekly_plan_v1"),
        "brand_name": str(cfg.get("brand_name") or "GenomeAI AgroAnimals"),
        "chart_count": len(chart_blocks),
        "chart_titles": [str(x.get("title") or x.get("key") or "") for x in chart_blocks],
        "page_count": int(page_count),
    }
    write_json(meta_path, meta)
    write_checksums(run_root=run_root)
    return {
        "ok": True,
        "plan_id": plan_id,
        "data_version": data_version,
        "run_root": str(run_root),
        "pdf_path": str(pdf_path),
        "pdf_rel_path": str(pdf_path.relative_to(Path(artifacts_root))),
        "meta_path": str(meta_path),
    }
