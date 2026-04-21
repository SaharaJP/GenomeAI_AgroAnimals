from __future__ import annotations

from pathlib import Path

from core.ai_daily_brief import build_daily_brief_markdown, build_daily_brief_share_seed, build_role_daily_brief


def _snapshot() -> dict:
    return {
        'data_version': 'dv_demo',
        'operational': {
            'alerts': {'new': 2, 'acknowledged': 1, 'resolved': 0},
            'tasks': {'open': 4, 'done': 2},
        },
        'report': {
            'has_any': True,
            'report_version': 'rv_demo',
            'qc_run': 'qc_demo',
            'model_version': 'mv_demo',
            'scoring_run': 'sr_demo',
        },
        'role_focus': {
            'top_candidates': 5,
            'high_risk_count': 3,
        },
    }


def test_t29_05_daily_brief_is_role_specific_reproducible_and_fact_linked() -> None:
    brief = build_role_daily_brief(role='Director', snapshot=_snapshot(), data_version='dv_demo')
    assert brief.role == 'Director'
    assert brief.data_version == 'dv_demo'
    assert brief.generated_mode == 'facts_template'
    assert brief.fallback_without_llm is True
    assert brief.source_versions['report_version'] == 'rv_demo'
    assert brief.brief_version.startswith('daily_brief::director::dv_demo::rv_demo')
    assert len(brief.items) >= 3

    first = brief.items[0]
    assert 'сигнал' in first.summary.lower() or 'alerts' in first.summary.lower()
    assert any(f.source_linkage == 'operational.alerts' for f in first.linked_facts)
    assert any(a.page.endswith('43_Daily_Worklists_By_Role.py') for a in first.linked_actions)
    assert any(a.expected_effect for a in first.linked_actions)


def test_t29_05_role_specific_variants_and_share_seed() -> None:
    zootech = build_role_daily_brief(role='Zootech', snapshot=_snapshot(), data_version='dv_demo')
    vet = build_role_daily_brief(role='Vet', snapshot=_snapshot(), data_version='dv_demo')

    assert any('кандидат' in item.summary.lower() for item in zootech.items)
    assert any('high-risk' in item.summary.lower() or 'клинический' in item.title.lower() for item in vet.items)

    seed = build_daily_brief_share_seed(brief=zootech)
    assert seed['ai_daily_brief.role'] == 'Zootech'
    assert seed['ai_daily_brief.data_version'] == 'dv_demo'
    assert 'brief_version' in seed['ai_daily_brief.brief_version'] or seed['ai_daily_brief.brief_version'].startswith('daily_brief::')


def test_t29_05_markdown_contains_linked_facts_actions_and_effect() -> None:
    brief = build_role_daily_brief(role='Operator', snapshot=_snapshot(), data_version='dv_demo')
    md = build_daily_brief_markdown(brief)
    assert '# Daily brief — Operator' in md
    assert 'source_versions:' in md
    assert 'Связанные факты:' in md
    assert 'Связанные действия:' in md
    assert 'Ожидаемый эффект:' in md


def test_t29_05_widget_and_pages_wired_and_docs_exist() -> None:
    helper = Path('streamlit_app/ai_daily_brief.py').read_text(encoding='utf-8')
    assert 'render_daily_brief_widget' in helper
    assert 'facts_template' in helper or 'fallback_without_llm' in helper
    assert 'Share via saved view' in helper
    assert 'Archive note' in helper
    assert 'Approval note' in helper

    home = Path('streamlit_app/home_v3.py').read_text(encoding='utf-8')
    assert 'render_daily_brief_widget' in home
    assert 'Открыть полный daily brief' in home

    report_view = Path('streamlit_app/pages/16_Report_View.py').read_text(encoding='utf-8')
    assert 'Открыть Daily Brief' in report_view

    page = Path('streamlit_app/pages/69_AI_Daily_Brief.py').read_text(encoding='utf-8')
    assert 'AI-generated daily brief' in page
    assert 'render_daily_brief_widget' in page

    docs = Path('docs/ai_generated_daily_brief.md').read_text(encoding='utf-8')
    assert 'role-specific daily brief' in docs
    assert 'fallback without LLM' in docs
    assert 'linked facts' in docs.lower()
    assert 'approval / archive / share' in docs.lower()

    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    assert '## T29-05 — AI-generated daily brief under governance' in assumptions
