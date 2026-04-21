from __future__ import annotations

from pathlib import Path

from streamlit_app.reports_ux import (
    build_report_catalog_rows,
    build_report_comment_rows,
    build_report_source_facts_rows,
    build_report_toc,
    build_saved_view_seed,
    filter_report_catalog_rows,
)
from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state


def test_build_report_toc_parses_markdown_headings() -> None:
    toc = build_report_toc("# Executive\ntext\n## Risks\n### Details")
    assert [row["title"] for row in toc] == ["Executive", "Risks", "Details"]
    assert [row["level"] for row in toc] == [1, 2, 3]



def test_build_report_catalog_rows_merges_regular_dashboard_and_approval() -> None:
    rows = build_report_catalog_rows(
        data_version="dv_demo",
        regular_entries=[
            {
                "report_version": "rep_01",
                "created_at_utc": "2026-03-29T10:00:00Z",
                "qc_run": "qc_01",
                "model_version": "model_01",
                "scoring_run": "score_01",
                "mode_requested": "fallback",
                "llm_used": False,
            }
        ],
        dashboard_items=[
            {
                "data_version": "dv_demo",
                "report_version": "rep_01",
                "created_at_utc": "2026-03-29T10:05:00Z",
                "dashboard_kind": "director_summary",
                "exports_dir": "/tmp/x",
            }
        ],
        approval_rows=[
            {
                "data_version": "dv_demo",
                "report_version": "rep_01",
                "status": "approved",
                "comment": "ok",
            }
        ],
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "mixed"
    assert row["approval_status"] == "approved"
    assert row["qc_run"] == "qc_01"
    assert row["dashboard_kinds"] == ["director_summary"]
    assert "approved" in row["search_text"]



def test_filter_report_catalog_rows_matches_query_kind_and_status() -> None:
    rows = [
        {"report_version": "rep_a", "kind": "regular", "approval_status": "draft", "search_text": "rep_a regular draft"},
        {"report_version": "rep_b", "kind": "dashboard", "approval_status": "approved", "search_text": "rep_b dashboard approved"},
    ]
    filtered = filter_report_catalog_rows(rows, query="rep_b", kind="dashboard", approval_status="approved")
    assert [row["report_version"] for row in filtered] == ["rep_b"]



def test_build_report_source_fact_and_comments_rows_include_approval() -> None:
    facts = build_report_source_facts_rows(
        entry={
            "data_version": "dv_demo",
            "qc_run": "qc_01",
            "model_version": "model_01",
            "scoring_run": "score_01",
            "report_version": "rep_01",
            "mode_requested": "fallback",
            "llm_used": False,
        },
        approval={"status": "archived", "comment": "old"},
    )
    comments = build_report_comment_rows(approval={"status": "archived", "comment": "old", "updated_at": "2026-03-29T10:00:00Z"})
    assert {row["fact"] for row in facts} >= {"data_version", "qc_run", "report_version", "approval_status"}
    assert comments == [{"status": "archived", "comment": "old", "updated_at": "2026-03-29T10:00:00Z"}]



def test_saved_view_seed_and_state_support_report_pages() -> None:
    seed_report = build_saved_view_seed(page_key="report_view", data_version="dv_demo", report_version="rep_01")
    seed_dash = build_saved_view_seed(page_key="dashboard_reports", data_version="dv_demo", report_version="rep_02", dashboard_kind="director_summary")
    session_state: dict[str, object] = {}
    applied = apply_saved_view_state(page_key="report_view", state=seed_report, session_state=session_state)
    assert seed_report["report_view.report_version"] == "rep_01"
    assert applied == ["report_view.data_version", "report_view.report_version"]
    assert extract_saved_view_state(page_key="dashboard_reports", session_state=seed_dash) == seed_dash



def test_report_pages_reference_new_reports_helper_and_saved_views_support() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_catalog = (repo_root / "streamlit_app" / "pages" / "10_Regular_Reports.py").read_text(encoding="utf-8")
    report_view = (repo_root / "streamlit_app" / "pages" / "16_Report_View.py").read_text(encoding="utf-8")
    saved_views = (repo_root / "streamlit_app" / "pages" / "17_Saved_Views_And_Favorites.py").read_text(encoding="utf-8")
    approvals = (repo_root / "streamlit_app" / "pages" / "40_Approvals_Center.py").read_text(encoding="utf-8")
    assert "build_report_catalog_rows" in report_catalog
    assert "build_report_toc" in report_view
    assert "report_view" in saved_views and "dashboard_reports" in saved_views
    assert "report_approval_action" in approvals
