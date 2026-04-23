from __future__ import annotations

from pathlib import Path

from core.training_onboarding import build_role_onboarding_kit, build_role_onboarding_markdown
from streamlit_app.unified_shell import build_shell_for_user, load_shell_config
import core.security as rbac


def _shell(role: str):
    cfg = load_shell_config()
    return build_shell_for_user(cfg=cfg, role=role, permissions=set(rbac.DEFAULT_ROLE_PERMISSIONS.get(role, [])), include_hidden=False)


def test_t30_02_role_onboarding_kits_are_role_aware_and_ui_consistent() -> None:
    director = build_role_onboarding_kit(role='Director', shell_sections=_shell('Director'))
    zootech = build_role_onboarding_kit(role='Zootech', shell_sections=_shell('Zootech'))
    vet = build_role_onboarding_kit(role='Vet', shell_sections=_shell('Vet'))
    operator = build_role_onboarding_kit(role='Operator', shell_sections=_shell('Operator'))
    admin = build_role_onboarding_kit(role='Admin', shell_sections=_shell('Admin'))

    assert director.start_of_day and zootech.start_of_day and vet.start_of_day and operator.start_of_day and admin.start_of_day
    assert any(step.page.endswith('68_Enterprise_Benchmark_Views.py') for step in director.start_of_day)
    assert any(step.page.endswith('43_Daily_Worklists_By_Role.py') for step in zootech.start_of_day)
    assert any(step.page.endswith('51_Vet_Triage_Queues.py') for step in vet.start_of_day)
    assert any(step.page.endswith('25_Jobs_Center.py') for step in operator.start_of_day)
    assert any(step.page.endswith('37_Admin_Observability_Release.py') for step in admin.start_of_day)
    assert all(step.do_items for step in zootech.start_of_day[:1])
    assert all(step.dont_items for step in vet.start_of_day[:1])
    assert all(step.diagnostics for step in operator.start_of_day[:1])


def test_t30_02_markdown_contains_start_of_day_do_dont_and_diagnostics() -> None:
    kit = build_role_onboarding_kit(role='Operator', shell_sections=_shell('Operator'))
    md = build_role_onboarding_markdown(kit)
    assert '# Onboarding kit — Operator' in md
    assert '## Start-of-day workflow' in md
    assert 'Do:' in md
    assert "Don't:" in md
    assert 'Diagnostics:' in md
    assert 'jobs' in md.lower() or 'qc' in md.lower()


def test_t30_02_widget_pages_docs_and_home_hooks_are_present() -> None:
    helper = Path('streamlit_app/training_onboarding.py').read_text(encoding='utf-8')
    assert 'render_onboarding_widget' in helper
    assert 'Download onboarding JSON' in helper
    assert 'Download onboarding Markdown' in helper
    assert 'Открыть полный onboarding kit' in helper

    page = Path('streamlit_app/pages/70_Training_Onboarding_By_Role.py').read_text(encoding='utf-8')
    assert 'Training & onboarding by role' in page
    assert 'render_onboarding_widget' in page
    assert 'Роль для preview' in page

    home = Path('streamlit_app/home_v3.py').read_text(encoding='utf-8')
    assert 'render_onboarding_widget' in home
    assert 'home_v3.onboarding' in home

    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assert 'training_onboarding_by_role' in ia
    assert 'pages/70_Training_Onboarding_By_Role.py' in ia

    docs = Path('docs/training_onboarding_by_role.md').read_text(encoding='utf-8')
    assert 'role-based onboarding kit' in docs
    assert 'in-product help hooks' in docs
    assert 'RBAC restrictions' in docs

    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    assert '## T30-02 — Training and onboarding kit by role' in assumptions
