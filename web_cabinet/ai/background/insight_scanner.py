"""Background AI-агент: проактивный сканер инсайтов фермы (MVP-N15).

Вызывается каждые 6 часов через APScheduler (insight_scanner_cron.py).
В demo-режиме работает с seeded данными без реального вызова Claude.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

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
    Применяет фильтр enabled_categories из insight_settings (user_id='cron').
    """
    settings = get_ai_settings()

    if settings.GENOMEAI_AI_DEMO_MODE:
        results = _load_seeded_scan_insights(farm_id)
    else:
        results = _run_live_scan(farm_id)

    enabled = _enabled_categories_for_farm(farm_id)
    if enabled is not None:
        results = [r for r in results if r.category in enabled]
    return results


def get_active_insights(farm_id: str) -> list[dict]:
    """Загружает активные и недавно удалённые инсайты фермы из БД.

    Включение soft-deleted строк — критично для дедупликации: AI-сканер не должен
    воссоздавать инсайт, который пользователь уже удалил.
    """
    try:
        from web_cabinet.insights_v1 import _conn
    except Exception as exc:
        logger.debug(f"get_active_insights: insights_v1 unavailable: {exc}")
        return []
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT payload_json FROM scanner_insights
                    WHERE farm_id = %s
                      AND (status IN ('to_check', 'to_follow_up') OR deleted_at IS NOT NULL)
                    ORDER BY generated_at_utc DESC
                    LIMIT 50
                    """,
                    (farm_id,),
                )
                rows = cur.fetchall()
        return [json.loads(r[0]) if isinstance(r[0], str) else (r[0] or {}) for r in rows]
    except Exception as exc:
        logger.debug(f"get_active_insights skipped: {exc}")
        return []


def save_insight(insight: ScannerInsight) -> None:
    """Сохраняет инсайт в Postgres через psycopg shim. Gracefully skips on errors.

    Также денормализует severity/body/action/animal_ids/recommendations
    в типизированные колонки (миграция 20260507_12_insights_extend) — фронту
    эти поля доступны без парсинга payload_json.
    """
    try:
        from web_cabinet.insights_v1 import _conn
    except Exception as exc:
        logger.debug(f"save_insight: insights_v1 unavailable: {exc}")
        return
    try:
        import json as _json
        recs_json = _json.dumps([
            r.model_dump() if hasattr(r, "model_dump") else dict(r)
            for r in (insight.recommendations or [])
        ])
        animal_ids_json = _json.dumps(list(insight.affected_cow_ids or []))
        body_text = getattr(insight, "description", "") or ""
        action_text = ""
        # If recommendations have an "action" field, prefer the first as `action`
        if insight.recommendations:
            first = insight.recommendations[0]
            action_text = getattr(first, "action", "") or getattr(first, "text", "") or ""
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scanner_insights
                      (insight_id, farm_id, title, category, priority, status,
                       generated_at_utc, generator, payload_json,
                       severity, body, action, animal_ids, recommendations)
                    VALUES (%s, %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s::jsonb, %s::jsonb)
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
                        insight.priority,           # severity mirrors priority for now
                        body_text,
                        action_text,
                        animal_ids_json,
                        recs_json,
                    ),
                )
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
        settings = get_ai_settings()
        ctx = build_farm_context(farm_id, settings=settings)
        context_text = _serialize_for_claude(ctx)
        existing = get_active_insights(farm_id)

        user_message = build_insight_scanner_message(context_text, existing)
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
        valid = _dedup_animal_category_7d(valid, existing)

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


def _serialize_for_claude(ctx: Any) -> str:
    """Serialize FarmContext for Claude with sensor_anomalies as a dedicated section."""
    import dataclasses as _dc

    if not hasattr(ctx, "farm_id"):
        return str(ctx)

    def _safe_dump(obj: Any) -> str:
        if _dc.is_dataclass(obj) and not isinstance(obj, type):
            obj = _dc.asdict(obj)
        return json.dumps(obj, ensure_ascii=False, default=str)

    parts = [f"Ферма: {ctx.farm_id}"]
    if getattr(ctx, "herd_summary", None):
        parts.append(f"Стадо: {_safe_dump(ctx.herd_summary)}")
    kpi = getattr(ctx, "kpi", None)
    if kpi is not None:
        parts.append(f"KPI: {_safe_dump(kpi)}")
    if getattr(ctx, "active_insights", None):
        parts.append(f"Активные тревоги: {_safe_dump(ctx.active_insights)}")
    if getattr(ctx, "recent_events", None):
        parts.append(f"Последние события: {_safe_dump(ctx.recent_events)}")
    if getattr(ctx, "attention_cows", None):
        parts.append(f"Коровы под наблюдением: {_safe_dump(ctx.attention_cows)}")
    anomalies = getattr(ctx, "sensor_anomalies", None)
    if anomalies:
        anom_list = [
            (_dc.asdict(a) if _dc.is_dataclass(a) and not isinstance(a, type) else vars(a))
            for a in anomalies
        ]
        parts.append(f"АНОМАЛИИ СЕНСОРОВ:\n{json.dumps(anom_list, ensure_ascii=False, default=str)}")
    return "\n".join(parts)


def _dedup_animal_category_7d(
    new_insights: list[ScannerInsight],
    existing: list[dict],
) -> list[ScannerInsight]:
    """Skip new insights if same (animal_id, category) was seen in existing within 7 days."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    recent_keys: set[tuple[str, str]] = set()
    for ex in existing:
        try:
            gen_at = datetime.fromisoformat(str(ex.get("generated_at_utc", "")))
            if gen_at < cutoff:
                continue
        except (ValueError, TypeError):
            continue
        category = ex.get("category", "")
        for cow_id in ex.get("affected_cow_ids", []):
            recent_keys.add((cow_id, category))
    result = []
    for ins in new_insights:
        if not any((cid, ins.category) in recent_keys for cid in ins.affected_cow_ids):
            result.append(ins)
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
    """Точка входа для APScheduler: обходит все активные фермы.

    Применяет cron-only token-saver gate: пропускает Claude-вызов, если с
    момента последнего скана не появилось новых событий, алертов или
    sensor-аномалий. Manual scan-now не использует этот gate.
    """
    from ..config import get_ai_settings
    settings = get_ai_settings()
    farms = [settings.GENOMEAI_DEMO_FARM_ID]
    logger.info(f"insight_scanner cron triggered farms={farms}")
    for farm_id in farms:
        if cron_should_skip_scan(farm_id):
            logger.info(f"insight_scanner skipped: no new inputs farm={farm_id}")
            _record_scan_run(farm_id, skipped=True, reason="no_new_inputs")
            continue
        insights = scan_for_new_insights(farm_id)
        _record_scan_run(farm_id, skipped=False, reason=None)
        if insights:
            _broadcast_new_insights(farm_id, len(insights))


def _broadcast_new_insights(farm_id: str, count: int) -> None:
    """Публикует событие в SSE-брокер после создания инсайтов."""
    try:
        from ..endpoints.insights_stream import broadcast_insights_event
        broadcast_insights_event(farm_id=farm_id, count=count)
    except Exception as exc:
        logger.debug(f"broadcast_new_insights skipped: {exc}")


def _enabled_categories_for_farm(farm_id: str) -> list[str] | None:
    """Returns enabled_categories from insight_settings (cron user), or None when no row.

    None means "no per-farm filter is configured" (allow all categories).
    Empty list means "no categories enabled" (filter out all results).
    """
    try:
        from web_cabinet.insights_v1 import _conn, _dict_cursor
    except Exception as exc:
        logger.debug(f"_enabled_categories_for_farm: insights_v1 unavailable: {exc}")
        return None
    try:
        with _conn() as conn:
            with _dict_cursor(conn) as cur:
                cur.execute(
                    "SELECT enabled_categories FROM insight_settings "
                    "WHERE user_id='cron' AND farm_id=%s",
                    (farm_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        cats = row.get("enabled_categories") if isinstance(row, dict) else row[0]
        if isinstance(cats, str):
            cats = json.loads(cats)
        return list(cats) if cats is not None else None
    except Exception as exc:
        logger.warning(f"_enabled_categories_for_farm failed farm={farm_id}: {exc}")
        return None


def cron_should_skip_scan(farm_id: str) -> bool:
    """Returns True when no new inputs since last_scan_at — cron may skip Claude.

    Inputs considered: timeline_events.created_at, alerts_v2.created_at,
    sensor anomalies in the recent window. Fails open (returns False) on any
    DB/error, so cron continues to run when state is uncertain.
    """
    try:
        from web_cabinet.insights_v1 import _conn
    except Exception as exc:
        logger.debug(f"cron_should_skip_scan: insights_v1 unavailable: {exc}")
        return False

    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_scan_at FROM insight_scan_state WHERE farm_id=%s",
                    (farm_id,),
                )
                row = cur.fetchone()
                last_scan_at = row[0] if row else None
                if last_scan_at is None:
                    return False  # never scanned -> always run

                # Cast last_scan_at to text in Postgres so both sides of the
                # comparison have the same canonical format (TIMESTAMPTZ::text
                # vs the TEXT-stored created_at columns).
                # 1. timeline_events (TEXT created_at; tenant_id may be farm_id or 'default')
                cur.execute(
                    """
                    SELECT 1 FROM timeline_events
                    WHERE tenant_id IN (%s, 'default')
                      AND created_at > (%s::timestamptz)::text
                    LIMIT 1
                    """,
                    (farm_id, last_scan_at),
                )
                if cur.fetchone():
                    return False

                # 2. alerts_v2 (best-effort; table may have different schema or be empty)
                try:
                    cur.execute(
                        """
                        SELECT 1 FROM alerts_v2
                        WHERE tenant_id IN (%s, 'default')
                          AND created_at > (%s::timestamptz)::text
                        LIMIT 1
                        """,
                        (farm_id, last_scan_at),
                    )
                    if cur.fetchone():
                        return False
                except Exception as alerts_exc:
                    logger.debug(f"cron_should_skip_scan: alerts_v2 check skipped: {alerts_exc}")

        # 3. sensor anomalies (window roughly proportional to time-since-scan)
        try:
            from web_cabinet.analytics.sensor_bridge import detect_recent_sensor_anomalies
            cutoff_naive = (
                last_scan_at.replace(tzinfo=None)
                if hasattr(last_scan_at, "replace")
                else datetime.utcnow()
            )
            delta_days = max(1, (datetime.utcnow() - cutoff_naive).days + 1)
            anomalies = detect_recent_sensor_anomalies(farm_id, lookback_days=delta_days)
            if anomalies:
                return False
        except Exception as exc:
            logger.debug(f"cron_should_skip_scan: sensor check skipped: {exc}")

        return True
    except Exception as exc:
        logger.warning(f"cron_should_skip_scan check failed farm={farm_id}: {exc}")
        return False  # fail open


def _record_scan_run(farm_id: str, *, skipped: bool, reason: Optional[str]) -> None:
    """Update insight_scan_state with the latest scan timestamp / skip reason."""
    try:
        from web_cabinet.insights_v1 import _conn
    except Exception:
        return
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO insight_scan_state (farm_id, last_scan_at, last_skipped_reason)
                    VALUES (%s, NOW(), %s)
                    ON CONFLICT (farm_id) DO UPDATE
                      SET last_scan_at = NOW(),
                          last_skipped_reason = EXCLUDED.last_skipped_reason
                    """,
                    (farm_id, reason if skipped else None),
                )
            conn.commit()
    except Exception as exc:
        logger.debug(f"_record_scan_run skipped: {exc}")
