from __future__ import annotations

from pathlib import Path

from streamlit_app.field_friendly_ui import build_field_chip_row_html, field_mode_enabled, get_field_resume_context, remember_field_resume_context


def test_t25_04_field_mode_and_resume_context_are_bounded_and_testable() -> None:
    assert field_mode_enabled(session_state={'ui.mobile_mode': True}, query_params={}) is True
    assert field_mode_enabled(session_state={'ui.mobile_mode': False}, query_params={'mobile': '1'}) is True
    state: dict[str, object] = {}
    payload = remember_field_resume_context(
        state,
        source_page='pages/58_Mobile_Worklists.py',
        source_label='Mobile worklists',
        object_type='animal',
        object_id='A-100',
        state={'round': 'vet', 'bucket': 'focus'},
    )
    assert payload['source_label'] == 'Mobile worklists'
    restored = get_field_resume_context(state)
    assert restored['object_type'] == 'animal'
    assert restored['state']['round'] == 'vet'


def test_t25_04_field_chip_row_html_is_high_signal_and_not_raw_table() -> None:
    html = build_field_chip_row_html({'priority': 'P1', 'due': 'overdue', 'confidence': '0.81'}, tone='warning')
    assert 'ga-field-chip-row' in html
    assert 'priority: P1' in html
    assert 'ga-field-chip--warning' in html


def test_t25_04_selected_pages_use_field_patterns_and_resume_flow() -> None:
    root = Path(__file__).resolve().parents[1]
    field_ui = (root / 'streamlit_app' / 'field_friendly_ui.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'field_friendly_ui_patterns.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    page58 = (root / 'streamlit_app' / 'pages' / '58_Mobile_Worklists.py').read_text(encoding='utf-8')
    page59 = (root / 'streamlit_app' / 'pages' / '59_Cowside_Event_Entry.py').read_text(encoding='utf-8')
    page15 = (root / 'streamlit_app' / 'pages' / '15_Animal_Profile.py').read_text(encoding='utf-8')
    page14 = (root / 'streamlit_app' / 'pages' / '14_Group_Profile.py').read_text(encoding='utf-8')

    assert 'render_field_resume_bar' in field_ui
    assert 'remember_field_resume_context' in page58
    assert 'render_field_chip_row' in page58
    assert 'render_field_resume_bar' in page59
    assert 'remember_field_resume_context' in page59
    assert 'render_field_resume_bar' in page15
    assert 'render_field_resume_bar' in page14
    assert 'field-friendly' in docs.lower()
    assert 'T25-04' in assumptions
