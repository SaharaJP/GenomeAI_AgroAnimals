"""Link timeline events to influenced metric_ids via AI (with static fallback)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from web_cabinet.ai.config import get_ai_settings

logger = logging.getLogger("genomeai.analytics.event_metric_linker")

# Static category map — used as fallback when Claude unavailable / demo mode
STATIC_MAP: dict[str, list[str]] = {
    "ration_change":   ["dmi", "feed_efficiency", "feed_cost", "milk_ecm"],
    "feed_change":     ["dmi", "feed_efficiency", "feed_cost", "milk_ecm"],
    "treatment":       ["health_issues", "mastitis", "milk_ecm"],
    "vet_visit":       ["health_issues", "mastitis"],
    "staffing":        ["milk_ecm", "milk_visits"],
    "calving":         ["repro_rates", "days_open", "milk_ecm"],
    "ai_insemination": ["repro_rates", "days_open"],
    "culling":         ["herd_size", "culling_rate"],
    "weather_event":   ["activity", "rumination", "milk_ecm"],
}


def link_event_to_metrics(event: dict[str, Any]) -> list[str]:
    """Return list of metric_ids influenced by this event. Empty list on failure."""
    settings = get_ai_settings()
    event_type = event.get("event_type") or ""
    if settings.GENOMEAI_AI_DEMO_MODE:
        return list(STATIC_MAP.get(event_type, []))
    try:
        result = _claude_link(event)
        if result:
            return result
    except Exception as exc:
        logger.warning(f"_claude_link failed: {exc}")
    # Live mode but Claude failed: fall back to static map
    return list(STATIC_MAP.get(event_type, []))


def _claude_link(event: dict[str, Any]) -> Optional[list[str]]:
    try:
        from web_cabinet.ai.client import get_client
    except Exception:
        return None
    metric_catalog = (
        "milk_ecm fat_protein scc dmi feed_cost feed_efficiency repro_rates "
        "days_open mastitis health_issues activity rumination herd_size milk_visits "
        "culling_rate"
    )
    prompt = (
        f"Event type='{event.get('event_type')}', title='{event.get('title','')}', "
        f"body='{(event.get('body') or '')[:200]}'.\n"
        f"Metric ids: {metric_catalog}.\n"
        "Reply with a JSON array of metric_id strings (subset of the list) that this "
        "event likely influences. Reply with ONLY the JSON array, no commentary."
    )
    import asyncio
    import json as _json

    client = get_client()
    loop = asyncio.new_event_loop()
    try:
        resp = loop.run_until_complete(
            client.agenerate(  # type: ignore[union-attr]
                prompt,
                system_prompt="You map farm events to affected metric ids.",
                task_type="event_metric_linker",
                max_tokens=120,
                temperature=0.0,
            )
        )
    finally:
        loop.close()
    raw = (resp.content or "").strip().strip("` \n")
    if raw.startswith("json"):
        raw = raw[4:].lstrip()
    try:
        data = _json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if isinstance(x, str)]
    except Exception:
        return None
    return None
