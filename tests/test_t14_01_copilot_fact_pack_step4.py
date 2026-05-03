from __future__ import annotations

from genomeai.copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack
from genomeai.copilot_target_resolver import (
    build_copilot_navigation_hints,
    build_copilot_web_target,
    parse_copilot_target,
    resolve_copilot_target_from_fact_pack,
)


def _demo_assistant_fact_pack() -> dict:
    fp = {
        "period": "daily",
        "asof_date": "2026-03-09",
        "versions": {"data_version": "dv_demo", "model_version": "mdl_001"},
        "modules": {
            "kpi": {
                "available": True,
                "run_id": "kpi_run_001",
                "kpi_count": 3,
                "alert_count": 1,
                "kpi_wide_top": [{"farm_id": "farm_1", "milk_kg": 123.4}],
                "sources": {
                    "kpi_summary": "/tmp/kpi_summary.json",
                    "kpi_wide": "/tmp/kpi_wide.csv",
                },
            }
        },
        "assistant_knowledge": {
            "regular_reports_latest": {
                "available": True,
                "report_version": "rep_daily_001",
                "sources": {"director_md": "/tmp/report_director.md"},
            }
        },
    }
    fp["copilot_fact_pack"] = build_copilot_fact_pack_from_assistant_fact_pack(fp)
    return fp


def test_parse_target_and_build_web_href() -> None:
    target = parse_copilot_target(
        target=(
            "genomeai://copilot/fact?data_version=dv_demo&section=modules.kpi&table=kpi_summary"
            "&metric=kpi_count&run_id=kpi_run_001&report_version=NA&fact_id=fact.modules_kpi.kpi_count"
        )
    )
    assert target["data_version"] == "dv_demo"
    assert target["section"] == "modules.kpi"
    assert target["metric"] == "kpi_count"
    web_href = build_copilot_web_target(target)
    assert web_href.startswith("/copilot/fact?")
    assert "data_version=dv_demo" in web_href
    assert "fact_id=fact.modules_kpi.kpi_count" in web_href


def test_resolve_fact_target_from_fact_pack_and_suggest_navigation() -> None:
    fp = _demo_assistant_fact_pack()
    target = parse_copilot_target(
        data_version="dv_demo",
        section="modules.kpi",
        metric="kpi_count",
        table="kpi_summary",
        run_id="kpi_run_001",
        fact_id="fact.modules_kpi.kpi_count",
    )
    resolution = resolve_copilot_target_from_fact_pack(fact_pack=fp, target=target)
    assert resolution["ok"] is True
    assert resolution["matched_kind"] == "fact"
    assert resolution["fact"]["value"] == 3
    assert resolution["sources"]
    assert any(str(row.get("ref") or "").endswith("kpi_summary.json") for row in resolution["sources"])

    hints = build_copilot_navigation_hints(target=target, resolution=resolution)
    hrefs = [row["href"] for row in hints]
    assert "/copilot/fact?data_version=dv_demo" in hrefs[0]
    assert "/reports?dv=dv_demo" in hrefs
    assert "/score?dv=dv_demo" in hrefs


def test_resolve_missing_data_request_when_section_has_no_facts() -> None:
    fp = {
        "period": "daily",
        "asof_date": "2026-03-09",
        "versions": {"data_version": "dv_empty", "model_version": "NA"},
        "modules": {},
        "assistant_knowledge": {},
    }
    target = parse_copilot_target(data_version="dv_empty", section="modules.repro")
    resolution = resolve_copilot_target_from_fact_pack(fact_pack=fp, target=target)
    assert resolution["ok"] is False
    assert resolution["matched_kind"] == "missing_data_request"
    req = resolution["missing_data_request"]
    assert req["section"] == "modules.repro"
    assert req["needed_data"]
    assert req["how_to_get"]
