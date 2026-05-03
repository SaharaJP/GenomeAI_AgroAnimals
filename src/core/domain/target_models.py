"""Canonical domain models for Target v2 and shared domain entities.

Legacy import path: genomeai.target.model_v2
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from core.domain.enums import (
    AlertSeverity,
    AnimalEventActorType,
    AnimalEventReasonCode,
    AnimalEventSource,
    AnimalEventType,
    EventSeverity,
    RecommendationDecision,
)

try:  # pydantic v2
    from pydantic import ConfigDict
    from pydantic import field_validator as _field_validator

    def field_validator(*args, **kwargs):  # type: ignore
        return _field_validator(*args, **kwargs)
except Exception:  # pragma: no cover - pydantic v1 fallback
    ConfigDict = None  # type: ignore
    from pydantic import validator as _validator

    def field_validator(*args, **kwargs):  # type: ignore
        return _validator(*args, **kwargs)

TenantId = str
Sex = Literal["F", "M", "U"]


class CanonicalBase(BaseModel):
    tenant_id: TenantId = Field(default="default", description="Tenant/organization scope")
    created_at: Optional[datetime] = Field(default=None, description="Record creation time (system)")
    updated_at: Optional[datetime] = Field(default=None, description="Record update time (system)")

    if ConfigDict is not None:  # pydantic v2
        model_config = ConfigDict(extra="forbid", use_enum_values=True, validate_default=True)
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"
            use_enum_values = True
            validate_all = True


class Farm(CanonicalBase):
    farm_id: str
    farm_name: str
    country_code: Optional[str] = Field(default=None, description="ISO-3166 alpha-2")
    timezone: Optional[str] = Field(default=None, description="IANA timezone, e.g. Europe/Berlin")
    currency: Optional[str] = Field(default="EUR", description="ISO-4217 currency code")


class Site(CanonicalBase):
    site_id: str
    farm_id: str
    site_name: str
    address: Optional[str] = None


class Pen(CanonicalBase):
    pen_id: str
    site_id: str
    pen_name: str
    pen_type: Optional[Literal["lactating", "dry", "heifer", "calf", "hospital", "other"]] = "other"
    capacity_head: Optional[int] = None


class Bull(CanonicalBase):
    bull_id: str
    bull_name: Optional[str] = None
    breed: Optional[str] = None


class Animal(CanonicalBase):
    animal_id: str
    farm_id: str
    site_id: Optional[str] = None
    current_pen_id: Optional[str] = None
    master_animal_id: Optional[str] = Field(default=None, description="Target master ID (T0-02)")
    external_id: Optional[str] = Field(default=None, description="Source system ID")
    sex: Sex = "U"
    birth_date: Optional[date] = None
    breed: Optional[str] = None
    status: Optional[Literal["active", "sold", "dead", "culled", "unknown"]] = "unknown"


class Lactation(CanonicalBase):
    lactation_id: str = Field(description="Surrogate stable ID for lactation (Target)")
    animal_id: str
    lactation_no: int = Field(ge=1, description="Parity index")
    calving_date: date
    dryoff_date: Optional[date] = None
    milk_305d_kg: Optional[float] = Field(default=None, ge=0.0, description="Standard 305d milk yield, kg")
    calving_outcome: Optional[Literal["normal", "abortion", "stillbirth", "unknown"]] = "unknown"

    @field_validator("dryoff_date")
    def _dry_after_calving(cls, v, info):  # type: ignore
        try:
            calving = info.data.get("calving_date")
        except Exception:
            calving = info.get("calving_date")
        if v is not None and calving is not None and v < calving:
            raise ValueError("dryoff_date must be >= calving_date")
        return v


class Event(CanonicalBase):
    event_id: str
    animal_id: str
    event_date: date
    event_type: str
    severity: EventSeverity = EventSeverity.UNKNOWN
    notes: Optional[str] = None


class AnimalEvent(CanonicalBase):
    event_id: str
    animal_id: str
    farm_id: Optional[str] = None
    site_id: Optional[str] = None
    lactation_id: Optional[str] = None
    event_type: AnimalEventType
    event_ts: datetime
    event_date: Optional[date] = None
    actor_type: AnimalEventActorType = AnimalEventActorType.UNKNOWN
    actor_user_id: Optional[int] = None
    actor_username: Optional[str] = None
    source: AnimalEventSource = AnimalEventSource.UNKNOWN
    source_ref: Optional[str] = None
    reason_code: Optional[str] = None
    linked_object_type: Optional[str] = None
    linked_object_id: Optional[str] = None
    linked_decision_id: Optional[str] = None
    linked_task_id: Optional[str] = None
    request_id: Optional[str] = None
    job_id: Optional[str] = None
    data_version: Optional[str] = None
    qc_run: Optional[str] = None
    model_version: Optional[str] = None
    scoring_run: Optional[str] = None
    report_version: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1)

    @field_validator("event_date", mode="before")
    def _default_event_date(cls, v, info):  # type: ignore
        if v is not None:
            return v
        try:
            event_ts = info.data.get("event_ts")
        except Exception:
            event_ts = info.get("event_ts")
        if isinstance(event_ts, datetime):
            return event_ts.date()
        return v

    @field_validator("reason_code")
    def _validate_reason_code(cls, v, info):  # type: ignore
        if v in (None, ""):
            return None
        value = str(v).strip()
        if not value:
            return None
        event_type = None
        try:
            event_type = info.data.get("event_type")
        except Exception:
            event_type = info.get("event_type")
        if value == AnimalEventReasonCode.CUSTOM_OTHER.value:
            return value
        if value not in {item.value for item in AnimalEventReasonCode}:
            raise ValueError(f"unknown animal event reason_code: {value}")
        if event_type == AnimalEventType.CUSTOM_OPERATIONAL_EVENT and value != AnimalEventReasonCode.CUSTOM_OTHER.value:
            return value
        return value

    @field_validator("linked_object_id")
    def _validate_linked_object_pair(cls, v, info):  # type: ignore
        try:
            linked_type = info.data.get("linked_object_type")
        except Exception:
            linked_type = info.get("linked_object_type")
        if bool(linked_type) ^ bool(v):
            raise ValueError("linked_object_type and linked_object_id must be provided together")
        return v


class MilkingsDaily(CanonicalBase):
    record_id: str
    animal_id: str
    lactation_id: Optional[str] = None
    date: date
    milk_kg: float = Field(ge=0.0)
    milking_count: Optional[int] = Field(default=None, ge=0)
    fat_pct: Optional[float] = Field(default=None, ge=0.0, le=15.0)
    protein_pct: Optional[float] = Field(default=None, ge=0.0, le=15.0)
    scc_cells_ml: Optional[int] = Field(default=None, ge=0)


class TestDay(CanonicalBase):
    testday_id: str
    animal_id: str
    lactation_id: Optional[str] = None
    test_date: date
    dim: Optional[int] = Field(default=None, ge=0, description="Days in milk")
    milk_kg: Optional[float] = Field(default=None, ge=0.0)
    fat_pct: Optional[float] = Field(default=None, ge=0.0, le=15.0)
    protein_pct: Optional[float] = Field(default=None, ge=0.0, le=15.0)
    scc_cells_ml: Optional[int] = Field(default=None, ge=0)


class SensorsDaily(CanonicalBase):
    record_id: str
    animal_id: str
    date: date
    activity_count: Optional[int] = Field(default=None, ge=0)
    rumination_min: Optional[int] = Field(default=None, ge=0)
    lying_min: Optional[int] = Field(default=None, ge=0)
    temperature_c: Optional[float] = Field(default=None)


class HealthEvent(Event):
    pass


class Treatment(CanonicalBase):
    treatment_id: str
    animal_id: str
    start_date: date
    end_date: Optional[date] = None
    treatment_type: str = Field(description="e.g. antibiotic, anti-inflammatory")
    reason_event_id: Optional[str] = Field(default=None, description="health_events.event_id")
    withdrawal_end_date: Optional[date] = None


class ReproEvent(CanonicalBase):
    repro_event_id: str
    animal_id: str
    event_date: date
    event_type: Literal["insemination", "preg_check", "heat", "calving", "abortion", "dryoff", "other"] = "other"
    bull_id: Optional[str] = None
    result: Optional[str] = None
    notes: Optional[str] = None


class PenMove(CanonicalBase):
    move_id: str
    animal_id: str
    from_pen_id: Optional[str] = None
    to_pen_id: str
    move_date: date
    reason: Optional[str] = None


class FeedRation(CanonicalBase):
    ration_id: str
    site_id: str
    ration_name: str
    effective_from: date
    effective_to: Optional[date] = None
    dm_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class FeedDelivery(CanonicalBase):
    delivery_id: str
    ration_id: str
    pen_id: str
    delivery_date: date
    feed_kg_as_fed: float = Field(ge=0.0)


class Price(CanonicalBase):
    price_id: str
    item_type: str = Field(description="e.g. milk, feed, vet")
    item_name: str
    currency: str = "EUR"
    unit: str = Field(description="e.g. kg, l, dose")
    valid_from: date
    valid_to: Optional[date] = None
    value: float


class EconomicsDaily(CanonicalBase):
    record_id: str
    farm_id: str
    date: date
    milk_price_per_kg: Optional[float] = None
    feed_cost_per_kg_dm: Optional[float] = None
    other_cost_eur: Optional[float] = None


class Alert(CanonicalBase):
    alert_id: str
    farm_id: str
    alert_date: date
    severity: AlertSeverity = AlertSeverity.INFO
    alert_type: str = Field(description="e.g. qc_error, health_risk, repro_delay")
    entity_type: Optional[str] = Field(default=None, description="animal|pen|farm|site|lactation")
    entity_id: Optional[str] = None
    message: str


class Decision(CanonicalBase):
    decision_id: str
    farm_id: str
    decision_date: date
    animal_id: Optional[str] = None
    lactation_id: Optional[str] = None
    recommendation_type: str
    decision: RecommendationDecision = RecommendationDecision.DEFER
    comment: Optional[str] = None
    source_alert_id: Optional[str] = None


class Report(CanonicalBase):
    report_id: str
    farm_id: str
    report_date: date
    report_type: str = Field(description="e.g. qc, scoring, weekly_ops")
    data_version: str
    run_id: str
    storage_path: str = Field(description="Path to DOCX/PDF in artifacts store")


class User(CanonicalBase):
    user_id: str
    username: str
    display_name: Optional[str] = None
    is_active: bool = True


class Role(CanonicalBase):
    role_id: str
    role_name: Literal["Admin", "Operator", "Viewer"]


class UserRole(CanonicalBase):
    user_id: str
    role_id: str


__all__ = [
    "Alert",
    "AnimalEvent",
    "Animal",
    "Bull",
    "CanonicalBase",
    "Decision",
    "EconomicsDaily",
    "Event",
    "Farm",
    "FeedDelivery",
    "FeedRation",
    "HealthEvent",
    "Lactation",
    "MilkingsDaily",
    "Pen",
    "PenMove",
    "Price",
    "Report",
    "ReproEvent",
    "Role",
    "SensorsDaily",
    "Sex",
    "Site",
    "TenantId",
    "TestDay",
    "Treatment",
    "User",
    "UserRole",
]
