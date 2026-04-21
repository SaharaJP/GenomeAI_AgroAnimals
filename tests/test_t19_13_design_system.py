from __future__ import annotations

from pathlib import Path

from streamlit_app.design_system import (
    build_detail_panel_html,
    build_filter_summary,
    build_page_header_html,
    build_section_header_html,
    build_status_chip_html,
    get_design_tokens,
)


def test_t19_13_design_tokens_expose_spacing_radius_and_tones() -> None:
    tokens = get_design_tokens()
    assert set(tokens.keys()) >= {"spacing", "radius", "font", "tones"}
    assert tokens["spacing"]["md"] == "0.85rem"
    assert tokens["radius"]["pill"] == "999px"
    assert set(tokens["tones"].keys()) >= {"neutral", "success", "warning", "danger", "info"}


def test_t19_13_status_chip_html_uses_stable_css_classes() -> None:
    html = build_status_chip_html(label="BLOCKER", tone="danger", icon="⛔")
    assert 'ga-chip' in html
    assert 'ga-chip--danger' in html
    assert 'BLOCKER' in html
    assert '⛔' in html


def test_t19_13_page_and_section_headers_include_badges_and_copy() -> None:
    page_html = build_page_header_html(
        title="QC Workspace",
        subtitle="Checks tree + issue grid",
        badges={"surface": "Operations", "pattern": "workspace"},
        status="Ready",
    )
    assert 'ga-page-header' in page_html
    assert 'QC Workspace' in page_html
    assert 'surface: Operations' in page_html
    assert 'pattern: workspace' in page_html
    assert 'Ready' in page_html

    section_html = build_section_header_html(
        title="Issue grid",
        caption="Переход от проблемы к строкам/датасетам/полям.",
        chips={"layer": "detail"},
    )
    assert 'ga-section-title' in section_html
    assert 'Issue grid' in section_html
    assert 'layer: detail' in section_html


def test_t19_13_filter_summary_hides_default_like_values() -> None:
    summary = build_filter_summary({"data_version": "dv_demo", "kind": "all", "status": "(all)", "role": "Director"})
    assert summary == 'data_version=dv_demo · role=Director'
    assert 'kind=' not in summary
    assert 'status=' not in summary


def test_t19_13_detail_panel_renders_key_values() -> None:
    html = build_detail_panel_html(rows={"data_version": "dv_demo", "qc_run": "qc_01"})
    assert 'ga-detail-panel' in html
    assert 'data_version' in html
    assert 'dv_demo' in html
    assert 'qc_run' in html


def test_t19_13_common_bootstraps_design_system() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / 'streamlit_app' / 'common.py').read_text(encoding='utf-8')
    assert 'from streamlit_app.design_system import ensure_design_system' in text
    assert 'ensure_design_system()' in text


def test_t19_13_selected_pages_use_design_system_patterns() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / 'streamlit_app' / 'home_v3.py',
        root / 'streamlit_app' / 'pages' / '26_Upload_And_Ingest_Wizard.py',
        root / 'streamlit_app' / 'pages' / '27_QC_Operations.py',
        root / 'streamlit_app' / 'pages' / '16_Report_View.py',
        root / 'streamlit_app' / 'pages' / '34_Admin_Console.py',
    ]
    for path in targets:
        text = path.read_text(encoding='utf-8')
        assert 'render_page_header(' in text, path.name
        assert 'render_filter_bar_summary(' in text, path.name
        assert 'render_section_header(' in text, path.name
