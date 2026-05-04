"""POST /api/ai/impact-narrative — narrative-интерпретация влияния события (MVP-N16)."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..cache import get_cache
from ..client import get_client
from ..config import get_ai_settings
from ..models import ImpactNarrative, ImpactNarrativeRequest
from ..prompts.impact_narrative import IMPACT_NARRATIVE_SYSTEM, build_impact_narrative_message

logger = logging.getLogger("genomeai.ai.endpoint.impact_narrative")
router = APIRouter()

_SEEDED_PATH = (
    Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "seeded_impact_narratives.json"
)
_TIMELINE_PATH = (
    Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "timeline_events_seeded.json"
)
_CACHE_TTL_SECONDS = 86400  # 24h — одно событие в одном окне = один narrative


@router.post("/impact-narrative", response_model=ImpactNarrative)
async def generate_impact_narrative(req: ImpactNarrativeRequest) -> ImpactNarrative:
    """Генерирует narrative-интерпретацию влияния события на показатели фермы.

    В demo-режиме возвращает seeded narrative из investor_v1/seeded_impact_narratives.json.
    В production-режиме вызывает Claude Sonnet и кэширует результат на 24 часа.
    """
    settings = get_ai_settings()
    cache = get_cache()
    cache_key = cache.make_key(
        "impact_narrative",
        {"event_id": req.event_id, "window": req.window, "farm_id": req.farm_id},
    )

    cached = cache.get(cache_key)
    if cached:
        try:
            return ImpactNarrative(**json.loads(cached))
        except Exception:
            pass

    try:
        if settings.GENOMEAI_AI_DEMO_MODE:
            narrative = _load_seeded_narrative(req.event_id, req.window)
        else:
            narrative = await _generate_via_llm(req, settings)

        cache.set(cache_key, narrative.model_dump_json(), ttl=_CACHE_TTL_SECONDS)
        return narrative

    except Exception as exc:
        logger.error(f"impact_narrative error event={req.event_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"impact_narrative_failed: {exc}") from exc


# ---------------------------------------------------------------------------
# demo mode
# ---------------------------------------------------------------------------

def _load_seeded_narrative(event_id: str, window: str) -> ImpactNarrative:
    """Загружает seeded narrative для demo-режима."""
    try:
        if _SEEDED_PATH.exists():
            records: list[dict] = json.loads(_SEEDED_PATH.read_text(encoding="utf-8"))
            for rec in records:
                if rec.get("event_id") == event_id:
                    rec_copy = dict(rec)
                    rec_copy["window"] = window
                    rec_copy.setdefault("generated_at", datetime.utcnow().isoformat())
                    return ImpactNarrative(**rec_copy)
    except Exception as exc:
        logger.warning(f"seeded narrative load failed: {exc}")
    return _fallback_narrative(event_id, window)


def _fallback_narrative(event_id: str, window: str) -> ImpactNarrative:
    return ImpactNarrative(
        event_id=event_id,
        window=window,
        narrative=(
            "Событие зафиксировано в журнале фермы. "
            "Данных до/после недостаточно для количественной оценки влияния. "
            "Рекомендуется проверить наличие метрик за указанный период."
        ),
        interpretation="neutral",
        significance="insignificant",
        recommendations=["Проверить наличие метрик за период события в системе мониторинга."],
        confidence=0.2,
        generation_model="demo-fallback",
    )


# ---------------------------------------------------------------------------
# production LLM path
# ---------------------------------------------------------------------------

async def _generate_via_llm(req: ImpactNarrativeRequest, settings: Any) -> ImpactNarrative:
    from web_cabinet.analytics.statistical_extension import compute_full_impact

    event = _load_event(req.event_id, req.farm_id)
    before_metrics, after_metrics = _compute_window_metrics(req.event_id, req.window, req.farm_id)
    related_events = _load_related_events(req.event_id, req.window, req.farm_id)

    stat_result = _compute_statistical_result(event, req.farm_id, req.window, compute_full_impact)

    user_msg = build_impact_narrative_message(
        event=event,
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        related_events=related_events,
        statistical_result=stat_result,
    )
    client = get_client()
    resp = client.generate(
        user_msg,
        system_prompt=IMPACT_NARRATIVE_SYSTEM,
        task_type="impact_narrative",
        max_tokens=800,
        temperature=0.3,
    )
    return _parse_response(resp.content, req.event_id, req.window, resp.model)


def _compute_statistical_result(
    event: dict, farm_id: str, window: str, compute_fn: Any
) -> Any | None:
    """Вычисляет StatisticalImpactResult для первичного KPI события."""
    try:
        raw_date = event.get("event_date") or event.get("date")
        if not raw_date:
            return None
        event_date = date.fromisoformat(str(raw_date)[:10])
        event_type = event.get("event_type", "unknown")
        affected_groups = event.get("affected_groups") or event.get("groups") or []
        if isinstance(affected_groups, str):
            affected_groups = [affected_groups]
        return compute_fn(
            farm_id=farm_id,
            event_date=event_date,
            event_type=event_type,
            affected_groups=list(affected_groups),
            kpi_metric="milk_yield",
            window=window,  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.warning(f"statistical_result compute failed event={event.get('timeline_event_id')}: {exc}")
        return None


def _load_event(event_id: str, farm_id: str) -> dict:
    """Загружает детали события из timeline seeded данных или DB."""
    try:
        if _TIMELINE_PATH.exists():
            events: list[dict] = json.loads(_TIMELINE_PATH.read_text(encoding="utf-8"))
            for ev in events:
                if ev.get("timeline_event_id") == event_id:
                    return ev
    except Exception:
        pass
    return {"timeline_event_id": event_id, "event_type": "unknown", "farm_id": farm_id}


def _compute_window_metrics(event_id: str, window: str, farm_id: str) -> tuple[dict, dict]:
    """Вычисляет before/after метрики для события в заданном окне.

    В production подключается к DB; в current state возвращает заглушку.
    Реальные данные берутся из impact_analyses_seeded.json при наличии.
    """
    _window_days = {"3d": 3, "1w": 7, "2w": 14, "4w": 28}
    days = _window_days.get(window, 7)

    analyses_path = _TIMELINE_PATH.parent / "impact_analyses_seeded.json"
    try:
        if analyses_path.exists():
            analyses: list[dict] = json.loads(analyses_path.read_text(encoding="utf-8"))
            for a in analyses:
                if a.get("timeline_event_id") == event_id:
                    metric = a.get("metric", "milk_yield")
                    before = {
                        metric: {
                            "value": a.get("baseline_kg_day"),
                            "period": f"до события ({days}д)",
                        }
                    }
                    after = {
                        metric: {
                            "value": a.get("actual_kg_day"),
                            "period": f"после события ({days}д)",
                        }
                    }
                    return before, after
    except Exception:
        pass

    return (
        {"milk_yield": {"value": None, "period": f"до события ({days}д)"}},
        {"milk_yield": {"value": None, "period": f"после события ({days}д)"}},
    )


def _load_related_events(event_id: str, window: str, farm_id: str) -> list[dict]:
    """Загружает смежные события в окне для учёта confounders."""
    try:
        if _TIMELINE_PATH.exists():
            events: list[dict] = json.loads(_TIMELINE_PATH.read_text(encoding="utf-8"))
            return [ev for ev in events if ev.get("timeline_event_id") != event_id][:5]
    except Exception:
        pass
    return []


def _parse_response(content: str, event_id: str, window: str, model: str) -> ImpactNarrative:
    """Парсит JSON-ответ LLM в ImpactNarrative."""
    raw = content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\ncontent={raw[:500]}") from exc

    return ImpactNarrative(
        event_id=event_id,
        window=window,
        narrative=data.get("narrative", ""),
        interpretation=data.get("interpretation", "neutral"),
        significance=data.get("significance", "minor"),
        recommendations=data.get("recommendations", []),
        confidence=float(data.get("confidence", 0.5)),
        generation_model=model,
    )
