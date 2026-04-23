"""POST /api/ai/insights/scan-now — ручной запуск сканера инсайтов (MVP-N15).

Только для admin. В demo-режиме возвращает seeded данные.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..models import ScanNowResponse, ScannerInsight

logger = logging.getLogger("genomeai.ai.endpoint.insights")
router = APIRouter()


@router.post("/insights/scan-now", response_model=ScanNowResponse)
async def scan_now(farm_id: str = Query(default="demo-farm-v1")) -> ScanNowResponse:
    """Запускает сканер инсайтов немедленно (manual trigger, admin only).

    В demo-режиме возвращает pre-seeded insights без вызова Claude.
    В production-режиме вызывает Claude Sonnet и возвращает реальные инсайты.
    Также пушит SSE-событие в открытые соединения.
    """
    from ..background.insight_scanner import scan_for_new_insights
    from ..config import get_ai_settings
    from .insights_stream import broadcast_insights_event

    settings = get_ai_settings()

    try:
        new_insights = scan_for_new_insights(farm_id)
    except Exception as exc:
        logger.error(f"scan_now failed farm={farm_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"scan_failed: {exc}") from exc

    count = len(new_insights)
    if count:
        broadcast_insights_event(farm_id=farm_id, count=count)
        logger.info(f"scan_now completed farm={farm_id} new_insights={count}")

    if count == 0:
        msg = "Новых аномалий не обнаружено."
    elif count == 1:
        msg = "Обнаружен 1 новый инсайт."
    else:
        msg = f"Обнаружено {count} новых инсайтов."

    return ScanNowResponse(
        farm_id=farm_id,
        new_insights=new_insights,
        message=msg,
        demo_mode=settings.GENOMEAI_AI_DEMO_MODE,
    )


@router.get("/insights/active", response_model=list[ScannerInsight])
async def get_active_insights(farm_id: str = Query(default="demo-farm-v1")) -> list[ScannerInsight]:
    """Возвращает активные инсайты фермы из БД.

    В demo-режиме возвращает seeded insights из investor_v1.
    """
    from ..background.insight_scanner import get_active_insights as _get_active
    from ..config import get_ai_settings

    settings = get_ai_settings()

    if settings.GENOMEAI_AI_DEMO_MODE:
        return _load_seeded_active_insights(farm_id)

    raw = _get_active(farm_id)
    results = []
    for rec in raw:
        try:
            results.append(ScannerInsight(**rec))
        except Exception:
            pass
    return results


def _load_seeded_active_insights(farm_id: str) -> list[ScannerInsight]:
    """Загружает seeded insights из investor_v1/insights_seeded.json для demo."""
    import json
    from pathlib import Path

    from ..background.insight_scanner import _insight_from_dict

    seeded_path = (
        Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "insights_seeded.json"
    )
    try:
        if seeded_path.exists():
            records = json.loads(seeded_path.read_text(encoding="utf-8"))
            results = []
            for rec in records:
                insight = _insight_from_dict(rec, farm_id)
                if insight is not None:
                    results.append(insight)
            return results
    except Exception as exc:
        logger.warning(f"seeded active insights load failed: {exc}")
    return []
