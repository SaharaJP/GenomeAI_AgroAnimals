from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from packages.contracts.api_boundary_v1 import FeedingRation, FeedIntakeDrop
from web_cabinet.feeding_v1 import load_rations, project_intake_drops


# ─── load_rations ──────────────────────────────────────────────────────────

def test_load_rations_missing_file_returns_empty(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    result = load_rations(cfg)
    assert result == []


def test_load_rations_empty_groups_returns_empty(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text("version: 1\ngroups: []\n", encoding="utf-8")
    result = load_rations(cfg)
    assert result == []


def test_load_rations_one_group(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text(
        "version: 1\n"
        "groups:\n"
        "  - group_id: GR-01\n"
        "    group_name: 'Group 1'\n"
        "    ration_name: 'TMR-A'\n"
        "    dm_kg: 18.5\n"
        "    last_distribution_at: '2026-05-15T06:30:00Z'\n"
        "    status: ok\n",
        encoding="utf-8",
    )
    result = load_rations(cfg)
    assert len(result) == 1
    item = result[0]
    assert isinstance(item, FeedingRation)
    assert item.group_id == "GR-01"
    assert item.group_name == "Group 1"
    assert item.ration_name == "TMR-A"
    assert item.dm_kg == pytest.approx(18.5)
    assert item.last_distribution_at == "2026-05-15T06:30:00Z"
    assert item.status == "ok"


def test_load_rations_skips_invalid_entries(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text(
        "version: 1\n"
        "groups:\n"
        "  - group_id: GR-01\n"
        "    group_name: 'OK group'\n"
        "    ration_name: 'TMR-A'\n"
        "  - 'not-a-dict'\n"
        "  - group_id: GR-02\n"
        "    ration_name: 'TMR-B'\n",
        encoding="utf-8",
    )
    result = load_rations(cfg)
    assert len(result) == 1
    assert result[0].group_id == "GR-01"


def test_load_rations_handles_malformed_yaml(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text("not: a: valid: yaml: list", encoding="utf-8")
    result = load_rations(cfg)
    assert result == []


# ─── project_intake_drops ──────────────────────────────────────────────────

def _insight(insight_id: str, type_: str, *, animal_ids=None, chart_data=None, title="t", body="b", date="2026-05-14"):
    return {
        "insight_id": insight_id,
        "type": type_,
        "severity": "info",
        "status": "to_check",
        "date": date,
        "animal_ids": animal_ids or [],
        "title": title,
        "body": body,
        "chart_data": chart_data or [],
    }


def test_project_intake_drops_filters_by_feed_related_type():
    insights = [
        _insight("I-1", "feed_intake_drop", animal_ids=["A-1", "A-2"], chart_data=[12.0, 9.0]),
        _insight("I-2", "mastitis_alert"),
        _insight("I-3", "dmi_drop", chart_data=[20.0, 14.0]),
    ]
    result = project_intake_drops(insights)
    ids = {item.insight_id for item in result}
    assert ids == {"I-1", "I-3"}
    for item in result:
        assert isinstance(item, FeedIntakeDrop)


def test_project_intake_drops_empty_input_returns_empty():
    assert project_intake_drops([]) == []


def test_project_intake_drops_no_matches_returns_empty():
    insights = [
        _insight("I-1", "mastitis_alert"),
        _insight("I-2", "lameness"),
    ]
    assert project_intake_drops(insights) == []


def test_project_intake_drops_extracts_title_and_date():
    insights = [
        _insight("I-1", "feed_intake_drop", title="Группа 1 — −18% DMI", date="2026-05-14"),
    ]
    result = project_intake_drops(insights)
    assert len(result) == 1
    assert result[0].title == "Группа 1 — −18% DMI"
    assert result[0].last_observed_at == "2026-05-14"


def test_project_intake_drops_handles_objects_with_attributes():
    class _O:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    insights = [_O(**_insight("I-1", "feed_intake_drop"))]
    result = project_intake_drops(insights)
    assert len(result) == 1
    assert result[0].insight_id == "I-1"
