"""AI describer for QC incidents. One Claude call per incident, cached in DB."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from web_cabinet.insights_v1 import _conn
from web_cabinet.ai.config import get_ai_settings

logger = logging.getLogger("genomeai.analytics.qc_ai_describer")

_SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "demo" / "investor_v1" / "qc_descriptions_seeded.json"
)


def _load_seed() -> dict[str, str]:
    try:
        return json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug(f"_load_seed failed: {exc}")
        return {}


def describe_qc_incident(incident_id: str) -> Optional[str]:
    """Generate ai_description for incident if missing.

    Returns the new description or None on failure. Idempotent: if the row
    already has ai_description set, returns it without doing any work.
    """
    settings = get_ai_settings()
    detector_type: Optional[str] = None
    root_cause: Optional[str] = None
    existing: Optional[str] = None
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT detector_type, root_cause, ai_description FROM qc_incidents "
                    "WHERE incident_id=%s",
                    (incident_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                detector_type, root_cause, existing = row
        if existing:
            return existing
    except Exception as exc:
        logger.warning(f"describe_qc_incident: load failed: {exc}")
        return None

    if settings.GENOMEAI_AI_DEMO_MODE:
        seed = _load_seed()
        text = seed.get(detector_type or "") or root_cause or "Возможный сбой данных."
    else:
        text = _claude_describe(detector_type, root_cause) or root_cause or "Возможный сбой данных."

    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE qc_incidents SET ai_description=%s WHERE incident_id=%s",
                    (text, incident_id),
                )
            conn.commit()
    except Exception as exc:
        logger.warning(f"describe_qc_incident: persist failed: {exc}")
        return None
    return text


def _claude_describe(detector_type: Optional[str], root_cause: Optional[str]) -> Optional[str]:
    try:
        from web_cabinet.ai.client import get_client
    except Exception as exc:
        logger.debug(f"_claude_describe: no client: {exc}")
        return None
    try:
        prompt = (
            f"QC sboj na ferme. Type: '{detector_type or ''}'. "
            f"Short label: '{root_cause or ''}'. "
            "Generate a Russian description (1-2 sentences) of what likely happened "
            "and why the data in this period is unreliable. No markdown."
        )
        import asyncio
        client = get_client()
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(
                client.agenerate(  # type: ignore[union-attr]
                    prompt,
                    system_prompt="You write short Russian QC explanations for farm operators.",
                    task_type="qc_describer",
                    max_tokens=200,
                    temperature=0.2,
                )
            )
        finally:
            loop.close()
        text = (resp.content or "").strip()
        return text or None
    except Exception as exc:
        logger.warning(f"_claude_describe failed: {exc}")
        return None
