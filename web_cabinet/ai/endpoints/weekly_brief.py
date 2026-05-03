"""POST /api/ai/weekly-brief — еженедельный аналитический брифинг фермы (MVP-N17)."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from ..cache import get_cache
from ..client import get_client
from ..config import get_ai_settings
from ..models import (
    Anomaly,
    BriefSection,
    DateRange,
    KeyRecommendation,
    WeeklyBrief,
    WeeklyBriefRequest,
)
from ..prompts.weekly_brief import WEEKLY_BRIEF_SYSTEM, build_weekly_brief_message

logger = logging.getLogger("genomeai.ai.endpoint.weekly_brief")
router = APIRouter()

_SEEDED_PATH = Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "weekly_briefs_seeded.json"
_CACHE_TTL_SECONDS = 604800  # 7 дней


# ---------------------------------------------------------------------------
# public helper (used by cron)
# ---------------------------------------------------------------------------

def _default_period() -> tuple[str, str]:
    today = date.today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


async def _generate_brief(
    farm_id: str,
    start_date: str = "",
    end_date: str = "",
    deliver_email: bool = False,
    force_regenerate: bool = False,
) -> WeeklyBrief:
    settings = get_ai_settings()
    if not start_date or not end_date:
        start_date, end_date = _default_period()

    cache = get_cache()
    cache_key = cache.make_key(
        "weekly_brief", {"farm_id": farm_id, "start": start_date, "end": end_date}
    )

    if not force_regenerate:
        cached = cache.get(cache_key)
        if cached:
            try:
                return WeeklyBrief(**json.loads(cached))
            except Exception:
                pass

    if settings.GENOMEAI_AI_DEMO_MODE:
        brief = _load_seeded_brief(farm_id, start_date, end_date)
        cache.set(cache_key, brief.model_dump_json(), ttl=_CACHE_TTL_SECONDS)
        if deliver_email:
            _send_email_stub(brief)
        return brief

    # Build farm context for the full period
    from ..context import build_farm_context
    try:
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)
        period_days = max((end_dt - start_dt).days + 1, 1)
    except ValueError:
        period_days = 7

    ctx = build_farm_context(farm_id, period_days=period_days)
    user_message = build_weekly_brief_message(ctx, start_date, end_date)
    client = get_client()
    resp = client.generate(
        user_message,
        system_prompt=WEEKLY_BRIEF_SYSTEM,
        task_type="weekly_brief",
        max_tokens=2500,
        temperature=0.3,
    )

    brief = _parse_response(
        resp.content, farm_id, start_date, end_date,
        resp.model, resp.input_tokens, resp.output_tokens,
    )
    _save_to_db(brief)
    cache.set(cache_key, brief.model_dump_json(), ttl=_CACHE_TTL_SECONDS)
    if deliver_email:
        _send_email_stub(brief)
    return brief


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

@router.post("/weekly-brief", response_model=WeeklyBrief)
async def generate_weekly_brief(req: WeeklyBriefRequest) -> WeeklyBrief:
    """Генерирует или возвращает кэшированный недельный брифинг для фермы."""
    try:
        return await _generate_brief(
            farm_id=req.farm_id,
            start_date=req.start_date,
            end_date=req.end_date,
            deliver_email=req.deliver_email,
            force_regenerate=req.force_regenerate,
        )
    except Exception as exc:
        logger.error(f"weekly_brief error farm={req.farm_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"weekly_brief_failed: {exc}") from exc


@router.get("/weekly-brief/latest", response_model=WeeklyBrief)
async def get_latest_weekly_brief(farm_id: str = "demo-farm-v1") -> WeeklyBrief:
    """GET-версия для dashboard — возвращает последний брифинг (генерирует при отсутствии)."""
    try:
        return await _generate_brief(farm_id=farm_id, force_regenerate=False)
    except Exception as exc:
        logger.error(f"weekly_brief latest error farm={farm_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"weekly_brief_failed: {exc}") from exc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_seeded_brief(farm_id: str, start_date: str, end_date: str) -> WeeklyBrief:
    try:
        if _SEEDED_PATH.exists():
            records = json.loads(_SEEDED_PATH.read_text(encoding="utf-8"))
            if records:
                for rec in records:
                    period = rec.get("period", {})
                    if period.get("start") == start_date and period.get("end") == end_date:
                        return _brief_from_seeded(rec, farm_id)
                return _brief_from_seeded(records[0], farm_id)
    except Exception as exc:
        logger.warning(f"seeded weekly_brief load failed: {exc}")
    return _fallback_brief(farm_id, start_date, end_date)


def _brief_from_seeded(rec: dict, farm_id: str) -> WeeklyBrief:
    period_raw = rec.get("period", {})
    period = DateRange(
        start=period_raw.get("start", ""),
        end=period_raw.get("end", ""),
    )

    sections = []
    for s in rec.get("sections", []):
        if isinstance(s, dict):
            sections.append(BriefSection(
                heading=s.get("heading", ""),
                narrative=s.get("narrative", ""),
                highlights=s.get("highlights", []),
                evidence_ids=s.get("evidence_ids", []),
            ))

    key_recs = []
    for r in rec.get("key_recommendations", []):
        if isinstance(r, dict):
            key_recs.append(KeyRecommendation(
                recommendation=r.get("recommendation", ""),
                priority=r.get("priority", "medium"),
                rationale=r.get("rationale", ""),
                expected_outcome=r.get("expected_outcome", ""),
                affected_entities=r.get("affected_entities", []),
            ))

    anomalies = []
    for a in rec.get("anomalies_detected", []):
        if isinstance(a, dict):
            anomalies.append(Anomaly(
                description=a.get("description", ""),
                severity=a.get("severity", "info"),
                evidence_id=a.get("evidence_id", ""),
            ))

    return WeeklyBrief(
        brief_id=rec.get("brief_id", f"wb_seeded_{period.end}"),
        farm_id=farm_id,
        period=period,
        title=rec.get("title", f"Недельный отчёт: {period.start} — {period.end}"),
        executive_summary=rec.get("executive_summary", ""),
        sections=sections,
        key_recommendations=key_recs,
        anomalies_detected=anomalies,
        kpi_table=rec.get("kpi_table", {}),
        generation_model="demo-seeded",
        generation_tokens={"input": 0, "output": 0},
    )


def _fallback_brief(farm_id: str, start_date: str, end_date: str) -> WeeklyBrief:
    return WeeklyBrief(
        farm_id=farm_id,
        period=DateRange(start=start_date, end=end_date),
        title=f"Недельный отчёт: {start_date} — {end_date}",
        executive_summary="Данные фермы недоступны. Брифинг в demo-режиме без фактических событий.",
        sections=[
            BriefSection(
                heading="Продуктивность",
                narrative="Demo-режим: реальные данные не подключены.",
            )
        ],
        key_recommendations=[
            KeyRecommendation(
                recommendation="Проверить доступность данных фермы",
                priority="medium",
                rationale="Реальные данные не загружены в систему",
                expected_outcome="Восстановление полноценного мониторинга",
            )
        ],
        anomalies_detected=[],
        kpi_table={},
        generation_model="demo-fallback",
        generation_tokens={"input": 0, "output": 0},
    )


def _parse_response(
    content: str,
    farm_id: str,
    start_date: str,
    end_date: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> WeeklyBrief:
    raw = content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\ncontent={raw[:500]}") from exc

    sections = []
    for s in data.get("sections", []):
        if isinstance(s, dict):
            sections.append(BriefSection(
                heading=s.get("heading", ""),
                narrative=s.get("narrative", ""),
                highlights=s.get("highlights", []),
                evidence_ids=s.get("evidence_ids", []),
            ))

    key_recs = []
    for r in data.get("key_recommendations", []):
        if isinstance(r, dict):
            key_recs.append(KeyRecommendation(
                recommendation=r.get("recommendation", ""),
                priority=r.get("priority", "medium"),
                rationale=r.get("rationale", ""),
                expected_outcome=r.get("expected_outcome", ""),
                affected_entities=r.get("affected_entities", []),
            ))

    anomalies = []
    for a in data.get("anomalies_detected", []):
        if isinstance(a, dict):
            anomalies.append(Anomaly(
                description=a.get("description", ""),
                severity=a.get("severity", "info"),
                evidence_id=a.get("evidence_id", ""),
            ))

    return WeeklyBrief(
        farm_id=farm_id,
        period=DateRange(start=start_date, end=end_date),
        title=data.get("title", f"Недельный отчёт: {start_date} — {end_date}"),
        executive_summary=data.get("executive_summary", ""),
        sections=sections,
        key_recommendations=key_recs,
        anomalies_detected=anomalies,
        kpi_table=data.get("kpi_table", {}),
        generation_model=model,
        generation_tokens={"input": input_tokens, "output": output_tokens},
    )


def _save_to_db(brief: WeeklyBrief) -> None:
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return
    try:
        import psycopg2  # type: ignore[import-untyped]
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO weekly_briefs
              (brief_id, farm_id, week_start, week_end, week_date,
               generated_at_utc, executive_summary, payload_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (brief_id) DO NOTHING
            """,
            (
                brief.brief_id,
                brief.farm_id,
                brief.period.start,
                brief.period.end,
                brief.period.end,
                brief.generated_at_utc.isoformat(),
                brief.executive_summary,
                brief.model_dump_json(),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"weekly_brief saved to db brief_id={brief.brief_id}")
    except Exception as exc:
        logger.warning(f"weekly_brief db save skipped: {exc}")


def _send_email_stub(brief: WeeklyBrief) -> None:
    """Email delivery stub — логирует факт отправки (SMTP не настроен)."""
    logger.info(
        f"weekly_brief email stub: would send brief_id={brief.brief_id} "
        f"farm_id={brief.farm_id} period={brief.period.start}..{brief.period.end}"
    )
