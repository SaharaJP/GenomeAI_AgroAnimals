from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProductionDayPoint(BaseModel):
    date: str
    avg_milk_kg: float
    ecm_kg: Optional[float] = None
    avg_fat_pct: Optional[float] = None
    avg_protein_pct: Optional[float] = None
    avg_scc_cells_ml: Optional[float] = None
    n_records: int


class ProductionSummary(BaseModel):
    avg_milk_kg: Optional[float] = None
    avg_ecm_kg: Optional[float] = None
    avg_fat_pct: Optional[float] = None
    avg_protein_pct: Optional[float] = None
    avg_scc_cells_ml: Optional[float] = None
    total_records: int


class ProductionResponse(BaseModel):
    schema: str = 'genomeai.api.analytics.production.v1'
    start_date: str
    end_date: str
    time_series: list[ProductionDayPoint] = Field(default_factory=list)
    summary: ProductionSummary


class ReproLactationDaysOpen(BaseModel):
    lactation_no: Optional[int] = None
    avg_days_open: Optional[float] = None
    n_animals: int


class ReproductionResponse(BaseModel):
    schema: str = 'genomeai.api.analytics.reproduction.v1'
    start_date: str
    end_date: str
    conception_rate: Optional[float] = None
    pregnancy_rate: Optional[float] = None
    days_open_by_lactation: list[ReproLactationDaysOpen] = Field(default_factory=list)
    vwp_days: int = 50
    inseminations: int = 0
    preg_checks: int = 0
    events_total: int = 0


class HealthIssueBreakdown(BaseModel):
    event_type: str
    count: int
    pct: float


class HealthResponse(BaseModel):
    schema: str = 'genomeai.api.analytics.health.v1'
    start_date: str
    end_date: str
    mastitis_count: int = 0
    health_issues_breakdown: list[HealthIssueBreakdown] = Field(default_factory=list)
    events_total: int = 0
