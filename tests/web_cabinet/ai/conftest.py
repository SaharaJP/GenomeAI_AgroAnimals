"""
Test fixtures for MVP-N12 context + tools tests.

The "rich_store" fixture builds an in-memory DemoDataStore with the
attention cows required by the N12 spec:
  - cow 4821 "Звёздочка"  — falling_yield + mastitis history
  - cow 7001 "Малина"      — ready_for_culling
  - cow 9002 "Ночка"       — high_scc

It also seeds 5 active treatments (for test_get_treatment_records_active).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure worktree root is importable before any project imports.
_wt_root = Path(__file__).resolve().parents[3]
if str(_wt_root) not in sys.path:
    sys.path.insert(0, str(_wt_root))

import datetime

import pandas as pd
import pytest

from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore


_TODAY = datetime.date(2026, 4, 22)
_D = lambda offset: (_TODAY + datetime.timedelta(days=offset)).isoformat()


# ---------------------------------------------------------------------------
# Animals
# ---------------------------------------------------------------------------

_ANIMALS = pd.DataFrame(
    [
        # cow 4821 Звёздочка — lactating Holstein
        dict(tenant_id="default", animal_id="4821", farm_id="FARM_TEST", site_id="SITE_1",
             current_pen_id="PEN_LACT", name="Звёздочка", sex="F", breed="Holstein", status="active"),
        # cow 7001 Малина — culling candidate
        dict(tenant_id="default", animal_id="7001", farm_id="FARM_TEST", site_id="SITE_1",
             current_pen_id="PEN_LACT", name="Малина", sex="F", breed="Holstein", status="active"),
        # cow 9002 Ночка — high SCC
        dict(tenant_id="default", animal_id="9002", farm_id="FARM_TEST", site_id="SITE_1",
             current_pen_id="PEN_LACT", name="Ночка", sex="F", breed="Holstein", status="active"),
        # cow 1001 — healthy reference
        dict(tenant_id="default", animal_id="1001", farm_id="FARM_TEST", site_id="SITE_1",
             current_pen_id="PEN_LACT", name="Ромашка", sex="F", breed="Holstein", status="active"),
    ]
)


# ---------------------------------------------------------------------------
# Milkings — Звёздочка: clear drop >10% over last 7 days
# ---------------------------------------------------------------------------

def _milkings() -> pd.DataFrame:
    rows = []
    # Звёздочка: 30kg earlier → 25kg recent (16.7% drop)
    for i in range(10, 0, -1):
        rows.append(dict(
            tenant_id="default", record_id=f"MK_4821_{i}",
            animal_id="4821", lactation_id="LAC_4821",
            date=_D(-i), milk_kg=30.0 if i > 7 else 25.0,
            milking_count=2, fat_pct=4.1, protein_pct=3.2,
            scc_cells_ml=180_000,
        ))
    # Малина: stable low 18 kg (low but not dropping)
    for i in range(10, 0, -1):
        rows.append(dict(
            tenant_id="default", record_id=f"MK_7001_{i}",
            animal_id="7001", lactation_id="LAC_7001",
            date=_D(-i), milk_kg=18.0, milking_count=2,
            fat_pct=3.8, protein_pct=3.1, scc_cells_ml=160_000,
        ))
    # Ночка: high SCC 350k
    for i in range(10, 0, -1):
        rows.append(dict(
            tenant_id="default", record_id=f"MK_9002_{i}",
            animal_id="9002", lactation_id="LAC_9002",
            date=_D(-i), milk_kg=26.0, milking_count=2,
            fat_pct=3.9, protein_pct=3.0, scc_cells_ml=350_000,
        ))
    # Reference cow 1001: healthy
    for i in range(10, 0, -1):
        rows.append(dict(
            tenant_id="default", record_id=f"MK_1001_{i}",
            animal_id="1001", lactation_id="LAC_1001",
            date=_D(-i), milk_kg=31.0, milking_count=2,
            fat_pct=4.0, protein_pct=3.3, scc_cells_ml=95_000,
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Health events — Звёздочка: mastitis 60+ days ago (for history test)
# ---------------------------------------------------------------------------

def _health_events() -> pd.DataFrame:
    return pd.DataFrame([
        # Звёздочка mastitis episode ~60 days ago
        dict(tenant_id="default", event_id="HE_4821_M1", animal_id="4821",
             event_date=_D(-62), event_type="mastitis", severity="high",
             notes="правая задняя четверть, SCC 680k"),
        dict(tenant_id="default", event_id="HE_4821_M2", animal_id="4821",
             event_date=_D(-58), event_type="mastitis", severity="medium",
             notes="follow-up, SCC 380k"),
        # Ночка: recent SCC anomaly
        dict(tenant_id="default", event_id="HE_9002_SCC", animal_id="9002",
             event_date=_D(-3), event_type="scc_spike", severity="warn",
             notes="SCC 350k — выше порога 200k"),
    ])


# ---------------------------------------------------------------------------
# Treatments — 5 active (covers test_get_treatment_records_active)
# ---------------------------------------------------------------------------

def _treatments() -> pd.DataFrame:
    return pd.DataFrame([
        # 3 currently active (start ≤ today ≤ end)
        dict(tenant_id="default", treatment_id="TR_001", animal_id="4821",
             start_date=_D(-5), end_date=_D(+3), treatment_type="mastitis_protocol",
             reason_event_id="HE_4821_M1", withdrawal_end_date=_D(+7)),
        dict(tenant_id="default", treatment_id="TR_002", animal_id="9002",
             start_date=_D(-2), end_date=_D(+5), treatment_type="pain_relief",
             reason_event_id="HE_9002_SCC", withdrawal_end_date=_D(+4)),
        dict(tenant_id="default", treatment_id="TR_003", animal_id="1001",
             start_date=_D(-1), end_date=_D(+6), treatment_type="antibiotic",
             reason_event_id="HE_1001_X", withdrawal_end_date=_D(+10)),
        dict(tenant_id="default", treatment_id="TR_004", animal_id="7001",
             start_date=_D(-3), end_date=_D(+2), treatment_type="vitamin_infusion",
             reason_event_id=None, withdrawal_end_date=_D(+2)),
        dict(tenant_id="default", treatment_id="TR_005", animal_id="7001",
             start_date=_D(-4), end_date=_D(+1), treatment_type="anti_inflammatory",
             reason_event_id=None, withdrawal_end_date=_D(+3)),
        # 1 completed
        dict(tenant_id="default", treatment_id="TR_OLD_001", animal_id="4821",
             start_date=_D(-65), end_date=_D(-60), treatment_type="mastitis_protocol",
             reason_event_id="HE_4821_M1", withdrawal_end_date=_D(-55)),
    ])


# ---------------------------------------------------------------------------
# Repro events
# ---------------------------------------------------------------------------

def _repro_events() -> pd.DataFrame:
    return pd.DataFrame([
        dict(tenant_id="default", repro_event_id="RE_001", animal_id="7001",
             event_date=_D(-15), event_type="insemination", bull_id="BULL_1",
             result="done", notes="AI cycle 2"),
        dict(tenant_id="default", repro_event_id="RE_002", animal_id="1001",
             event_date=_D(-10), event_type="heat", bull_id=None,
             result="candidate", notes="heat watch"),
        dict(tenant_id="default", repro_event_id="RE_003", animal_id="9002",
             event_date=_D(-20), event_type="preg_check_due", bull_id=None,
             result="due", notes="60d check due"),
    ])


# ---------------------------------------------------------------------------
# Decisions — Малина: culling recommended
# ---------------------------------------------------------------------------

def _decisions() -> pd.DataFrame:
    return pd.DataFrame([
        dict(tenant_id="default", decision_id="DEC_001", farm_id="FARM_TEST",
             decision_date=_D(-5), animal_id="7001", lactation_id="LAC_7001",
             recommendation_type="cull", decision="accept",
             comment="NPV отрицательный, 3-я лактация, хромота", source_alert_id=None),
    ])


# ---------------------------------------------------------------------------
# Pens
# ---------------------------------------------------------------------------

def _pens() -> pd.DataFrame:
    return pd.DataFrame([
        dict(tenant_id="default", pen_id="PEN_LACT", site_id="SITE_1",
             pen_name="Лактирующие", pen_type="lactating", capacity_head=200),
    ])


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------

def _economics() -> pd.DataFrame:
    return pd.DataFrame([
        dict(tenant_id="default", record_id="EC_001", farm_id="FARM_TEST",
             date=_D(-1), milk_price_per_kg=0.53, milk_price_ccy="EUR",
             feed_cost_per_kg_dm=0.31, feed_cost_ccy="EUR", other_cost_eur=148.0),
        dict(tenant_id="default", record_id="EC_002", farm_id="FARM_TEST",
             date=_D(0), milk_price_per_kg=0.53, milk_price_ccy="EUR",
             feed_cost_per_kg_dm=0.31, feed_cost_ccy="EUR", other_cost_eur=152.0),
    ])


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def _alerts() -> pd.DataFrame:
    return pd.DataFrame([
        dict(tenant_id="default", alert_id="AL_001", farm_id="FARM_TEST",
             alert_date=_D(0), severity="high", alert_type="vet_triage",
             entity_type="animal", entity_id="4821",
             message="Звёздочка: SCC нарастающий тренд, требуется осмотр"),
        dict(tenant_id="default", alert_id="AL_002", farm_id="FARM_TEST",
             alert_date=_D(0), severity="warn", alert_type="milk_quality",
             entity_type="animal", entity_id="9002",
             message="Ночка: SCC >200k за последние 7 дней"),
    ])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rich_store() -> DemoDataStore:
    """In-memory store with attention cows Звёздочка/Малина/Ночка."""
    return DemoDataStore.from_dataframes(
        dm_animals=_ANIMALS,
        dm_milkings_daily=_milkings(),
        dm_health_events=_health_events(),
        dm_treatments=_treatments(),
        dm_repro_events=_repro_events(),
        dm_decisions=_decisions(),
        dm_pens=_pens(),
        dm_economics_daily=_economics(),
        dm_alerts=_alerts(),
    )


@pytest.fixture(scope="session")
def csv_store() -> DemoDataStore:
    """Store loaded from demo_farm_v1 CSV files."""
    return DemoDataStore()
