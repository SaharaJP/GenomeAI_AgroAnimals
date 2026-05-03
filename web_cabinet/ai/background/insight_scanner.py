"""Background AI-агент: проактивный сканер инсайтов фермы (MVP-N15).

Вызывается каждые 6 часов через APScheduler (insight_scanner_cron.py).
В demo-режиме работает с seeded данными без реального вызова Claude.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_ai_settings
from ..models import ScannerInsight, ScannerRecommendation

# Imported at module level so tests can patch via the scanner module namespace.
try:
    from ..client import get_client
    from ..context import build_farm_context
    from ..prompts.insight_scanner import INSIGHT_SCANNER_SYSTEM, build_insight_scanner_message
except Exception:  # pragma: no cover — missing optional deps
    get_client = None  # type: ignore[assignment]
    build_farm_context = None  # type: ignore[assignment]
    INSIGHT_SCANNER_SYSTEM = ""  # type: ignore[assignment]
    build_insight_scanner_message = None  # type: ignore[assignment]

logger = logging.getLogger("genomeai.ai.insight_scanner")

_SCAN_NOW_SEEDED_PATH = (
    Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "scan_now_seeded.json"
)
_MAX_INSIGHTS_PER_SCAN = 5
_MIN_EVIDENCE_IDS = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_for_new_insights(farm_id: str) -> list[ScannerInsight]:
    """Сканирует данные фермы и создаёт новые инсайты.

    В demo-режиме возвращает seeded данные без вызова Claude.
    В production-режиме вызывает Claude Sonnet с full farm context.
    """
    settings = get_ai_settings()

    if settings.GENOMEAI_AI_DEMO_MODE:
        return _load_seeded_scan_insights(farm_id)

    return _run_live_scan(farm_id)


def get_active_insights(farm_id: str) -> list[dict]:
    """Загружает активные инсайты фермы из БД (или пустой список при недоступности)."""
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return []
    try:
        import psycopg2  # type: ignore[import-untyped]
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT payload_json FROM scanner_insights
            WHERE farm_id = %s AND status IN ('to_check', 'to_follow_up')
            ORDER BY generated_at_utc DESC
            LIMIT 20
            """,
            (farm_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [json.loads(r[0]) for r in rows]
    except Exception as exc:
        logger.debug(f"get_active_insights skipped: {exc}")
        return []


def save_insight(insight: ScannerInsight) -> None:
    """Сохраняет инсайт в Postgres. Gracefully skips if DB unavailable."""
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return
    try:
        import psycopg2  # type: ignore[import-untyped]
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scanner_insights
              (insight_id, farm_id, title, category, priority, status,
               generated_at_utc, generator, payload_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (insight_id) DO NOTHING
            """,
            (
                insight.insight_id,
                insight.farm_id,
                insight.title,
                insight.category,
                insight.priority,
                insight.status,
                insight.generated_at_utc.isoformat(),
                insight.generator,
                insight.model_dump_json(),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"insight saved insight_id={insight.insight_id} farm={insight.farm_id}")
    except Exception as exc:
        logger.warning(f"insight db save skipped: {exc}")


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def _load_seeded_scan_insights(farm_id: str) -> list[ScannerInsight]:
    """Возвращает seeded инсайты для demo-режима."""
    try:
        if _SCAN_NOW_SEEDED_PATH.exists():
            records = json.loads(_SCAN_NOW_SEEDED_PATH.read_text(encoding="utf-8"))
            results = []
            for rec in records[:_MAX_INSIGHTS_PER_SCAN]:
                insight = _insight_from_dict(rec, farm_id)
                if insight is not None:
                    results.append(insight)
            return results
    except Exception as exc:
        logger.warning(f"seeded scan_now load failed: {exc}")
    return []


# ---------------------------------------------------------------------------
# Live scan (production mode)
# ---------------------------------------------------------------------------

def _run_live_scan(farm_id: str) -> list[ScannerInsight]:
    """Вызывает Claude для поиска аномалий на живых данных фермы."""
    import asyncio

    try:
        ctx = build_farm_context(farm_id, period_days=1, include_cow_details=True)
        existing = get_active_insights(farm_id)

        user_message = build_insight_scanner_message(ctx, existing)
        client = get_client()

        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(
                client.agenerate(  # type: ignore[union-attr]
                    user_message,
                    system_prompt=INSIGHT_SCANNER_SYSTEM,
                    task_type="insight_scanner",
                    max_tokens=3000,
                    temperature=0.2,
                )
            )
        finally:
            loop.close()

        new_insights = _parse_insights(resp.content, farm_id)
        valid = [i for i in new_insights if _validate_evidence(i)]
        valid = _deduplicate(valid, existing)

        for insight in valid:
            save_insight(insight)

        logger.info(
            f"insight_scanner completed farm={farm_id} "
            f"found={len(new_insights)} valid={len(valid)}"
        )
        return valid

    except Exception as exc:
        logger.error(f"insight_scanner failed farm={farm_id}: {exc}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Parse + validate
# ---------------------------------------------------------------------------

def _parse_insights(content: str, farm_id: str) -> list[ScannerInsight]:
    """Парсит JSON-массив инсайтов из ответа LLM."""
    raw = content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"insight_scanner LLM JSON parse error: {exc} | raw={raw[:200]}")
        return []

    if not isinstance(data, list):
        logger.warning("insight_scanner: LLM returned non-list JSON")
        return []

    results = []
    for item in data[:_MAX_INSIGHTS_PER_SCAN]:
        insight = _insight_from_dict(item, farm_id)
        if insight is not None:
            results.append(insight)
    return results


def _insight_from_dict(rec: dict[str, Any], farm_id: str) -> ScannerInsight | None:
    """Конвертирует dict в ScannerInsight с мягкой валидацией."""
    try:
        title = rec.get("title", "")
        description = rec.get("description", rec.get("body", ""))
        if not title or not description:
            return None

        recs = []
        for r in rec.get("recommendations", []):
            if isinstance(r, dict):
                recs.append(ScannerRecommendation(
                    action=r.get("action", ""),
                    priority=r.get("priority", "medium"),
                    role=r.get("role", "operator"),
                    due_hint=r.get("due_hint"),
                ))

        # Graceful fallback: older seeded format uses animal_ids
        cow_ids = rec.get("affected_cow_ids") or rec.get("animal_ids") or []

        return ScannerInsight(
            insight_id=rec.get("insight_id") or f"ins_{uuid.uuid4().hex[:8]}",
            farm_id=farm_id,
            title=title,
            description=description,
            category=_coerce_category(rec.get("category", rec.get("type", "production"))),
            priority=_coerce_priority(rec.get("priority", rec.get("severity", "medium"))),
            status=rec.get("status", "to_check"),
            affected_cow_ids=cow_ids,
            affected_group_ids=rec.get("affected_group_ids", []),
            evidence_ids=rec.get("evidence_ids", []),
            recommendations=recs,
            generated_at_utc=datetime.utcnow(),
            generator=rec.get("generator", "ai_scanner"),
        )
    except Exception as exc:
        logger.debug(f"insight_from_dict skipped: {exc} | rec={rec}")
        return None


def _validate_evidence(insight: ScannerInsight) -> bool:
    """Инсайт валиден, если есть хотя бы один evidence_id."""
    return len(insight.evidence_ids) >= _MIN_EVIDENCE_IDS


def _deduplicate(
    new_insights: list[ScannerInsight],
    existing: list[dict],
) -> list[ScannerInsight]:
    """Убирает инсайты с полностью совпадающим набором evidence_ids."""
    existing_evidence_sets = {
        frozenset(e.get("evidence_ids", [])) for e in existing if e.get("evidence_ids")
    }
    result = []
    for ins in new_insights:
        key = frozenset(ins.evidence_ids)
        if key and key not in existing_evidence_sets:
            result.append(ins)
            existing_evidence_sets.add(key)
    return result


def _coerce_category(raw: str) -> str:
    _VALID = {"production", "reproduction", "health", "feeding", "welfare", "economics"}
    _MAP = {
        "health_alert": "health",
        "yield_drop_analysis": "production",
        "culling_recommendation": "economics",
        "pregnancy_rate": "reproduction",
        "scc_trend": "health",
        "heat_detection": "reproduction",
        "withdrawal_compliance": "health",
        "benchmark": "economics",
        "dim_group_analysis": "health",
        "upcoming_events": "reproduction",
        "feed_efficiency": "feeding",
    }
    v = raw.lower() if raw else "production"
    return v if v in _VALID else _MAP.get(v, "production")


def _coerce_priority(raw: str) -> str:
    _VALID = {"high", "medium", "low"}
    _MAP = {"urgent": "high", "critical": "high", "warn": "medium", "warning": "medium", "info": "low"}
    v = raw.lower() if raw else "medium"
    return v if v in _VALID else _MAP.get(v, "medium")


# ---------------------------------------------------------------------------
# Cron entry point
# ---------------------------------------------------------------------------

def run_insight_scanner_for_all_farms() -> None:
    """Точка входа для APScheduler: обходит все активные фермы."""
    from ..config import get_ai_settings
    settings = get_ai_settings()
    farms = [settings.GENOMEAI_DEMO_FARM_ID]
    logger.info(f"insight_scanner cron triggered farms={farms}")
    for farm_id in farms:
        insights = scan_for_new_insights(farm_id)
        if insights:
            _broadcast_new_insights(farm_id, len(insights))


def _broadcast_new_insights(farm_id: str, count: int) -> None:
    """Публикует событие в SSE-брокер после создания инсайтов."""
    try:
        from ..endpoints.insights_stream import broadcast_insights_event
        broadcast_insights_event(farm_id=farm_id, count=count)
    except Exception as exc:
        logger.debug(f"broadcast_new_insights skipped: {exc}")
