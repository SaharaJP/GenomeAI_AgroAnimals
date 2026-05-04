"""POST /api/impact — statistical impact analysis for farm events (PMV-B03).

Demo mode: compute_full_impact() is called with seeded event metadata,
yielding deterministic results identical across runs.
Real mode: same computation, demo_mode flag is False.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import get_ai_settings
from ..models import ImpactRequest, ImpactResponse, KpiImpactResult
from web_cabinet.analytics.statistical_extension import compute_full_impact

logger = logging.getLogger("genomeai.ai.endpoint.impact")
router = APIRouter()

_TIMELINE_PATH = (
    Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "timeline_events_seeded.json"
)

# Fallback metadata for DEMO_* events (sourced from timeline.ts DEMO_TIMELINE_EVENTS)
_DEMO_EVENT_META: dict[str, dict] = {
    "DEMO_001": {"event_date": date(2026, 3, 11), "event_type": "ration_change",       "affected_groups": ["pen_1", "pen_12", "pen_2"]},
    "DEMO_002": {"event_date": date(2026, 3, 6),  "event_type": "new_employee",        "affected_groups": ["pen_1"]},
    "DEMO_003": {"event_date": date(2026, 2, 25), "event_type": "feeding_schedule",    "affected_groups": ["pen_dry"]},
    "DEMO_004": {"event_date": date(2026, 2, 19), "event_type": "ration_change",       "affected_groups": ["pen_7"]},
    "DEMO_005": {"event_date": date(2026, 2, 15), "event_type": "ration_change",       "affected_groups": ["pen_1"]},
    "DEMO_006": {"event_date": date(2026, 2, 7),  "event_type": "hoof_trim",           "affected_groups": ["pen_all"]},
    "DEMO_007": {"event_date": date(2026, 1, 25), "event_type": "pen_density",         "affected_groups": ["pen_closeup"]},
    "DEMO_008": {"event_date": date(2026, 1, 17), "event_type": "bedding",             "affected_groups": ["pen_3"]},
}

_FALLBACK_META: dict = {
    "event_date": date(2026, 1, 1),
    "event_type": "unknown",
    "affected_groups": ["pen_1"],
}


@router.post("/impact", response_model=ImpactResponse)
async def compute_impact(req: ImpactRequest) -> ImpactResponse:
    """Return Welch t-test p-value, Cohen's d, and bootstrap CI for each requested KPI.

    In both demo and real mode the same statistical engine runs; the demo_mode
    flag only informs the client whether to treat results as illustrative.
    """
    settings = get_ai_settings()
    demo_mode: bool = settings.GENOMEAI_AI_DEMO_MODE

    event_meta = _load_event_meta(req.event_id)

    results: list[KpiImpactResult] = []
    for kpi in req.kpi_list:
        try:
            stat = compute_full_impact(
                farm_id=req.farm_id,
                event_date=event_meta["event_date"],
                event_type=event_meta["event_type"],
                affected_groups=event_meta["affected_groups"],
                kpi_metric=kpi,
                window=req.window,
            )
        except Exception as exc:
            logger.error(f"compute_full_impact failed kpi={kpi} event={req.event_id}: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"impact_compute_failed: {exc}") from exc

        results.append(KpiImpactResult(
            kpi=kpi,
            welch_t_pvalue=stat.welch_t_pvalue,
            cohen_d_effect_size=stat.cohen_d_effect_size,
            bootstrap_ci_95=stat.bootstrap_ci_95,
            significance=stat.significance,
            effect_magnitude=stat.effect_magnitude,
            diff_in_diff_effect=stat.diff_in_diff_effect,
            treated_before=stat.treated_before,
            treated_after=stat.treated_after,
            sample_sizes=stat.sample_sizes,
        ))

    return ImpactResponse(
        event_id=req.event_id,
        farm_id=req.farm_id,
        window=req.window,
        results=results,
        demo_mode=demo_mode,
    )


def _load_event_meta(event_id: str) -> dict:
    """Return event_date, event_type, affected_groups for an event.

    Checks DEMO_* hardcoded map first, then timeline_events_seeded.json.
    """
    if event_id in _DEMO_EVENT_META:
        return _DEMO_EVENT_META[event_id]

    try:
        if _TIMELINE_PATH.exists():
            events: list[dict] = json.loads(_TIMELINE_PATH.read_text(encoding="utf-8"))
            for ev in events:
                if ev.get("timeline_event_id") == event_id:
                    date_str: str = ev.get("date") or ev.get("timestamp", "")[:10]
                    try:
                        ev_date = date.fromisoformat(date_str)
                    except ValueError:
                        ev_date = _FALLBACK_META["event_date"]
                    return {
                        "event_date": ev_date,
                        "event_type": ev.get("event_type", "unknown"),
                        "affected_groups": ev.get("animal_ids") or _FALLBACK_META["affected_groups"],
                    }
    except Exception as exc:
        logger.warning(f"event meta load failed for {event_id}: {exc}")

    return dict(_FALLBACK_META)
