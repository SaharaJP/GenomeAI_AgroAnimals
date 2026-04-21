"""Системные промпты для всех AI use-cases GenomeAI."""
from .ask_farm import ASK_FARM_SYSTEM, build_ask_farm_message
from .morning_brief import MORNING_BRIEF_SYSTEM, build_morning_brief_message
from .weekly_brief import WEEKLY_BRIEF_SYSTEM, build_weekly_brief_message
from .insight_scanner import INSIGHT_SCANNER_SYSTEM, build_insight_scanner_message
from .impact_narrative import IMPACT_NARRATIVE_SYSTEM, build_impact_narrative_message
from .insight_narrative import INSIGHT_NARRATIVE_SYSTEM, build_insight_narrative_message

__all__ = [
    "ASK_FARM_SYSTEM",
    "build_ask_farm_message",
    "MORNING_BRIEF_SYSTEM",
    "build_morning_brief_message",
    "WEEKLY_BRIEF_SYSTEM",
    "build_weekly_brief_message",
    "INSIGHT_SCANNER_SYSTEM",
    "build_insight_scanner_message",
    "IMPACT_NARRATIVE_SYSTEM",
    "build_impact_narrative_message",
    "INSIGHT_NARRATIVE_SYSTEM",
    "build_insight_narrative_message",
]
