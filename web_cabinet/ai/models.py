"""Pydantic схемы для всех AI endpoints и use-cases GenomeAI."""
from __future__ import annotations

import uuid
from datetime import date as _date
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AskFarmEvidence(BaseModel):
    event_id: str
    description: str


class AskFarmRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    farm_id: str = "demo-farm-v1"
    user_id: str = "anonymous"
    include_context: bool = True


class AskFarmResponse(BaseModel):
    answer: str
    evidence: list[AskFarmEvidence] = []
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    latency_ms: float = 0.0


class Insight(BaseModel):
    id: str
    title: str
    description: str
    severity: str = Field(..., pattern="^(critical|warning|info)$")
    evidence: list[AskFarmEvidence] = []
    recommendation: str
    deadline_hours: Optional[int] = None
    cow_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Morning Brief V2 (MVP-N14)
# ---------------------------------------------------------------------------

class OvernightChange(BaseModel):
    text: str
    evidence_id: Optional[str] = None


class TodayAction(BaseModel):
    action: str
    priority: Literal["high", "medium", "low"]
    due: Optional[str] = None
    role: Literal["vet", "zootech", "operator", "director"]


class MorningBriefRequest(BaseModel):
    farm_id: str = "demo-farm-v1"
    force_regenerate: bool = False


class MorningBrief(BaseModel):
    brief_id: str = Field(default_factory=lambda: f"mb_{uuid.uuid4().hex[:12]}")
    farm_id: str
    generated_at_utc: datetime = Field(default_factory=datetime.utcnow)
    date: _date = Field(default_factory=_date.today)
    headline: str
    main_takeaway: str
    overnight_changes: list[OvernightChange] = []
    today_actions: list[TodayAction] = []
    notes: list[str] = []
    generation_model: str
    generation_tokens: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Weekly Brief
# ---------------------------------------------------------------------------

class WeeklyBrief(BaseModel):
    week_start: str
    week_end: str
    farm_id: str
    executive_summary: str
    kpi_analysis: str
    top_insights: list[Insight] = []
    recommendations: list[str] = []
    trend_summary: str = ""
    model: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    input_tokens: int = 0
    output_tokens: int = 0


class ImpactAnalysis(BaseModel):
    event_id: str
    event_type: str
    animal_id: Optional[str] = None
    impact_score: float = Field(..., ge=0.0, le=10.0)
    financial_impact_rub: Optional[float] = None
    description: str
    timeline: str = ""
    evidence: list[AskFarmEvidence] = []
    recommendations: list[str] = []
    model: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class InsightNarrative(BaseModel):
    insight_id: str
    title: str
    narrative: str
    root_cause: str
    evidence: list[AskFarmEvidence] = []
    recommended_actions: list[str] = []
    urgency: str = Field(..., pattern="^(immediate|today|this_week|monitor)$")
    model: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AIHealthResponse(BaseModel):
    status: str
    model: str
    demo_mode: bool
    cache_enabled: bool
    api_configured: bool


# ---------------------------------------------------------------------------
# Insight Scanner V2 (MVP-N15)
# ---------------------------------------------------------------------------

class ScannerRecommendation(BaseModel):
    action: str
    priority: Literal["high", "medium", "low"]
    role: Literal["vet", "zootech", "operator", "director"]
    due_hint: Optional[str] = None


class ScannerInsight(BaseModel):
    insight_id: str = Field(default_factory=lambda: f"ins_{uuid.uuid4().hex[:12]}")
    farm_id: str
    title: str
    description: str
    category: Literal["production", "reproduction", "health", "feeding", "welfare", "economics"]
    priority: Literal["high", "medium", "low"]
    status: Literal["to_check", "to_follow_up", "done"] = "to_check"
    affected_cow_ids: list[str] = []
    affected_group_ids: list[str] = []
    evidence_ids: list[str] = []
    recommendations: list[ScannerRecommendation] = []
    generated_at_utc: datetime = Field(default_factory=datetime.utcnow)
    generator: str = "ai_scanner"


class ScanNowResponse(BaseModel):
    farm_id: str
    new_insights: list[ScannerInsight]
    message: str
    demo_mode: bool = True


# ---------------------------------------------------------------------------
# Impact Narrative (MVP-N16)
# ---------------------------------------------------------------------------

class ImpactNarrativeRequest(BaseModel):
    event_id: str
    window: Literal["3d", "1w", "2w", "4w"] = "1w"
    language: str = "ru"
    farm_id: str = "demo-farm-v1"


class ImpactNarrative(BaseModel):
    event_id: str
    window: str
    narrative: str
    interpretation: Literal["positive", "negative", "neutral", "mixed"]
    significance: Literal["major", "moderate", "minor", "insignificant"]
    recommendations: list[str]
    confidence: float = Field(..., ge=0.0, le=1.0)
    generation_model: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
