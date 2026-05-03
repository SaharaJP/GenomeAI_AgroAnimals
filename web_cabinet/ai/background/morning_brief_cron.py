"""APScheduler cron: генерация утреннего брифинга в 06:00 MSK."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("genomeai.ai.cron.morning_brief")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False
    BackgroundScheduler = None  # type: ignore[misc,assignment]


def get_active_farms() -> list[str]:
    from web_cabinet.ai.config import get_ai_settings
    settings = get_ai_settings()
    return [settings.GENOMEAI_DEMO_FARM_ID]


def generate_morning_brief_sync(farm_id: str) -> None:
    """Вызывает генерацию брифинга для одной фермы (синхронно, для cron)."""
    import asyncio
    from web_cabinet.ai.endpoints.morning_brief import _generate_brief

    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_generate_brief(farm_id=farm_id, force_regenerate=False))
        finally:
            loop.close()
        logger.info(f"morning_brief generated ok farm={farm_id}")
    except Exception as exc:
        logger.error(f"morning_brief failed farm={farm_id} err={exc}", exc_info=True)


def run_daily_morning_brief() -> None:
    """Точка входа для APScheduler: обходит активные фермы."""
    farms = get_active_farms()
    logger.info(f"morning_brief cron triggered farms={farms}")
    for farm_id in farms:
        generate_morning_brief_sync(farm_id)


_scheduler: BackgroundScheduler | None = None  # type: ignore[type-arg]


def start_cron() -> None:
    global _scheduler
    if not _HAS_APSCHEDULER:
        logger.warning("apscheduler not installed — morning_brief cron disabled")
        return

    if _scheduler is not None and _scheduler.running:
        return

    import pytz
    tz = pytz.timezone("Europe/Moscow")

    cron_test = os.getenv("GENOMEAI_AI_CRON_TEST", "false").lower() == "true"

    _scheduler = BackgroundScheduler(timezone=tz)

    if cron_test:
        # Test mode: fire 1 minute from now (one-shot)
        from datetime import datetime, timedelta
        run_at = datetime.now(tz) + timedelta(minutes=1)
        _scheduler.add_job(
            run_daily_morning_brief,
            "date",
            run_date=run_at,
            id="morning_brief_test",
        )
        logger.info(f"morning_brief cron TEST mode: will fire at {run_at.isoformat()}")
    else:
        _scheduler.add_job(
            run_daily_morning_brief,
            "cron",
            hour=6,
            minute=0,
            id="morning_brief_daily",
        )
        logger.info("morning_brief cron registered: 06:00 MSK daily")

    _scheduler.start()


def stop_cron() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
