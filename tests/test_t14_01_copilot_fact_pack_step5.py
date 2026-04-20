from __future__ import annotations

from genomeai.copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack
from genomeai.copilot_target_resolver import build_copilot_detail_actions, parse_copilot_target, resolve_copilot_target_from_fact_pack
from genomeai.copilot_ui_links import build_citation_action_cards


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


def test_detail_actions_include_run_preview_and_api_links() -> None:
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
    actions = build_copilot_detail_actions(target=target, resolution=resolution)
    hrefs = [row["href"] for row in actions]
    assert any(h.startswith("/copilot/fact?") and "data_version=dv_demo" in h and "section=modules.kpi" in h and "table=kpi_summary" in h and "metric=kpi_count" in h and "run_id=kpi_run_001" in h and "fact_id=fact.modules_kpi.kpi_count" in h for h in hrefs)
    assert any(row.endswith("#table-preview") for row in hrefs)
    assert "/jobs?q=kpi_run_001" in hrefs
    assert "/reports?dv=dv_demo" in hrefs
    assert any(h.startswith("/api/copilot/fact?") and "data_version=dv_demo" in h and "run_id=kpi_run_001" in h and "fact_id=fact.modules_kpi.kpi_count" in h for h in hrefs)


def test_build_citation_action_cards_returns_absolute_urls() -> None:
    cards = build_citation_action_cards(
        [
            {
                "label": "modules.kpi.kpi_summary",
                "source": "/tmp/kpi_summary.json",
                "data_version": "dv_demo",
                "run_id": "kpi_run_001",
                "report_version": "NA",
                "section": "modules.kpi",
                "table": "kpi_summary",
                "metric": "kpi_count",
                "fact_id": "fact.modules_kpi.kpi_count",
            }
        ],
        web_base_url="http://copilot.local:8000",
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["resolver_url"].startswith("http://copilot.local:8000/copilot/fact?")
    assert card["preview_url"].endswith("#table-preview")
    assert card["jobs_url"] == "http://copilot.local:8000/jobs?q=kpi_run_001"
    assert card["reports_url"] == "http://copilot.local:8000/reports?dv=dv_demo"
