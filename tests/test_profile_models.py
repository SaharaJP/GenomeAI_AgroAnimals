"""Tests for animal profile Pydantic models."""
import pytest
from packages.contracts.api_boundary_v1 import (
    AnimalAttributes,
    HealthMetrics,
    ProfileResponse,
    ProfileSummary,
    EntityRef,
)


def test_animal_attributes_all_optional():
    obj = AnimalAttributes()
    assert obj.name is None
    assert obj.breed is None
    assert obj.birth_date is None
    assert obj.lactation_number is None
    assert obj.days_in_milk is None
    assert obj.last_calving_date is None
    assert obj.total_calvings is None
    assert obj.reproduction_status is None
    assert obj.next_calving_expected is None
    assert obj.group_label is None
    assert obj.farm_label is None


def test_animal_attributes_full():
    obj = AnimalAttributes(
        name="Ночка",
        breed="Голштинская",
        birth_date="2022-03-15",
        lactation_number=3,
        days_in_milk=45,
        last_calving_date="2026-03-12",
        total_calvings=3,
        reproduction_status="Ожидает",
        next_calving_expected=None,
        group_label="Группа 2",
        farm_label="Ферма Восток",
    )
    assert obj.name == "Ночка"
    assert obj.lactation_number == 3
    assert obj.farm_label == "Ферма Восток"


def test_health_metrics_defaults():
    hm = HealthMetrics()
    assert hm.activity_score is None
    assert hm.activity_norm == 60.0
    assert hm.scc is None
    assert hm.scc_trend is None
    assert hm.body_condition_score is None
    assert hm.daily_milk_yield_kg is None


def test_profile_response_without_animal_fields():
    pr = ProfileResponse(
        entity=EntityRef(object_type="animal", object_id="3142"),
        summary=ProfileSummary(),
    )
    assert pr.animal_attributes is None
    assert pr.health_metrics is None


def test_profile_response_with_animal_fields():
    pr = ProfileResponse(
        entity=EntityRef(object_type="animal", object_id="3142"),
        summary=ProfileSummary(),
        animal_attributes=AnimalAttributes(name="Ночка"),
        health_metrics=HealthMetrics(daily_milk_yield_kg=18.2),
    )
    assert pr.animal_attributes.name == "Ночка"
    assert pr.health_metrics.daily_milk_yield_kg == 18.2
