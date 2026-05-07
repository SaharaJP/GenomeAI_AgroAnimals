"""APScheduler cron: insight_scanner (every 6h :15) + qc_detector (every 6h :30)."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("genomeai.ai.cron")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False
    BackgroundScheduler = None  # type: ignore[misc,assignment]

_scheduler: "BackgroundScheduler | None" = None  # type: ignore[type-arg]


def start_cron() -> None:
    global _scheduler
    if not _HAS_APSCHEDULER:
        logger.warning("apscheduler not installed — cron jobs disabled")
        return

    if _scheduler is not None and _scheduler.running:
        return

    import pytz
    tz = pytz.timezone("Europe/Moscow")

    cron_test = os.getenv("GENOMEAI_AI_CRON_TEST", "false").lower() == "true"

    _scheduler = BackgroundScheduler(timezone=tz)

    if cron_test:
        from datetime import datetime, timedelta
        run_at = datetime.now(tz) + timedelta(minutes=2)
        _scheduler.add_job(
            _run_scanner,
            "date",
            run_date=run_at,
            id="insight_scanner_test",
        )
        run_at_qc = datetime.now(tz) + timedelta(minutes=3)
        _scheduler.add_job(
            _run_qc_scanner,
            "date",
            run_date=run_at_qc,
            id="qc_detector_test",
        )
        logger.info(
            f"cron TEST mode: insight at {run_at.isoformat()}, qc at {run_at_qc.isoformat()}"
        )
    else:
        _scheduler.add_job(
            _run_scanner,
            "cron",
            hour="*/6",
            minute=15,
            id="insight_scanner_6h",
        )
        _scheduler.add_job(
            _run_qc_scanner,
            "cron",
            hour="*/6",
            minute=30,
            id="qc_detector_6h",
        )
        logger.info("cron registered: insight_scanner @*/6:15, qc_detector @*/6:30 MSK")

    _scheduler.start()


def stop_cron() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _run_scanner() -> None:
    from .insight_scanner import run_insight_scanner_for_all_farms
    try:
        run_insight_scanner_for_all_farms()
    except Exception as exc:
        logger.error(f"insight_scanner cron job failed: {exc}", exc_info=True)


def _run_qc_scanner() -> None:
    from web_cabinet.analytics.qc_detector import run_qc_scan_for_all_farms
    try:
        run_qc_scan_for_all_farms()
    except Exception as exc:
        logger.error(f"qc_detector cron job failed: {exc}", exc_info=True)
