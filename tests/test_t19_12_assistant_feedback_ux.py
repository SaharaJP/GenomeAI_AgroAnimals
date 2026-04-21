from __future__ import annotations

from pathlib import Path

from streamlit_app.assistant_feedback_ux import (
    build_contextual_prompts,
    build_contextual_question,
    build_feedback_event_metadata,
    compact_versions_payload,
)


def test_t19_12_prompt_library_covers_required_contexts() -> None:
    for key in ["home", "alert", "animal_profile", "group_profile", "report_view"]:
        prompts = build_contextual_prompts(key)
        assert len(prompts) >= 3
        assert all(p.label and p.instruction for p in prompts)


def test_t19_12_contextual_question_contains_versions_and_object_refs() -> None:
    q = build_contextual_question(
        context_kind="alert",
        title="High SCC",
        instruction="Объясни, что делать дальше.",
        object_type="animal",
        object_id="A-100",
        data_version="dv_demo",
        qc_run="qc_01",
        model_version="model_01",
        scoring_run="score_01",
        report_version="rep_01",
        related_alert="alert_01",
        extra_context="severity=high",
    )
    assert "Контекст страницы: alert" in q
    assert "Объект: animal A-100" in q
    assert "data_version=dv_demo" in q
    assert "qc_run=qc_01" in q
    assert "model_version=model_01" in q
    assert "scoring_run=score_01" in q
    assert "report_version=rep_01" in q
    assert "related_alert=alert_01" in q
    assert "severity=high" in q
    assert "fact-pack" in q.lower()


def test_t19_12_versions_and_feedback_metadata_are_traceable() -> None:
    versions = compact_versions_payload(
        data_version="dv_demo",
        qc_run="qc_01",
        model_version="model_01",
        scoring_run="score_01",
        report_version="rep_01",
    )
    assert versions["data_version"] == "dv_demo"
    assert versions["report_version"] == "rep_01"

    meta = build_feedback_event_metadata(
        context_kind="report_view",
        title="Report rep_01",
        object_type="report",
        object_id="rep_01",
        source_versions=versions,
        assistant_query_id="query_01",
        assistant_guardrails={"fact_pack_only": True},
        panel_key="report_view.rep_01",
    )
    payload = meta["assistant_context"]
    assert payload["context_kind"] == "report_view"
    assert payload["object_type"] == "report"
    assert payload["object_id"] == "rep_01"
    assert payload["source_versions"]["data_version"] == "dv_demo"
    assert payload["query_id"] == "query_01"


def test_t19_12_required_pages_reference_contextual_panel() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "streamlit_app" / "home_v3.py",
        root / "streamlit_app" / "pages" / "5_Alert_Center_v2.py",
        root / "streamlit_app" / "pages" / "14_Group_Profile.py",
        root / "streamlit_app" / "pages" / "15_Animal_Profile.py",
        root / "streamlit_app" / "pages" / "16_Report_View.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "render_contextual_assistant_panel(" in text, path.name
