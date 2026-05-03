from __future__ import annotations

from pathlib import Path

from core.commercial_packaging import (
    build_packaging_summary,
    load_commercial_packaging_config,
    load_runtime_packaging_context,
    render_packaging_markdown,
)
from streamlit_app.ia_v3 import build_nav_for_user, load_ia_config
from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config
import core.security as rbac


def test_t30_04_runtime_packaging_resolves_profiles_and_env_override() -> None:
    foundation = load_runtime_packaging_context(project_root='.', env={'GENOMEAI_COMMERCIAL_PROFILE': 'foundation_default'})
    assert foundation.edition_key == 'foundation'
    assert foundation.enabled_modules == ()
    assert 'operational_core' in foundation.enabled_features
    assert 'economics' not in foundation.enabled_features

    override = load_runtime_packaging_context(
        project_root='.',
        env={'GENOMEAI_EDITION': 'professional', 'GENOMEAI_ENABLED_MODULES': 'economics,embedded_ai'},
    )
    assert override.edition_key == 'professional'
    assert set(override.enabled_modules) == {'economics', 'embedded_ai'}
    assert 'economics' in override.enabled_features
    assert 'embedded_ai' in override.enabled_features
    assert override.source == 'env'


def test_t30_04_shell_and_nav_filter_pages_by_enabled_modules() -> None:
    shell_cfg = load_shell_config()
    ia_cfg = load_ia_config()
    role = rbac.ROLE_DIRECTOR
    perms = set(rbac.DEFAULT_ROLE_PERMISSIONS.get(role, []))

    foundation = load_runtime_packaging_context(project_root='.', env={'GENOMEAI_COMMERCIAL_PROFILE': 'foundation_default'})
    enterprise = load_runtime_packaging_context(project_root='.', env={'GENOMEAI_COMMERCIAL_PROFILE': 'enterprise_default'})

    foundation_shell = flatten_shell_sections(
        build_shell_for_user(
            cfg=shell_cfg,
            role=role,
            permissions=perms,
            enabled_features=foundation.enabled_features,
            enabled_modules=foundation.enabled_modules,
        )
    )
    enterprise_shell = flatten_shell_sections(
        build_shell_for_user(
            cfg=shell_cfg,
            role=role,
            permissions=perms,
            enabled_features=enterprise.enabled_features,
            enabled_modules=enterprise.enabled_modules,
        )
    )
    assert 'enterprise_benchmark_views' not in foundation_shell
    assert 'migration_verification_toolkit' not in foundation_shell
    assert 'economics_v2' not in foundation_shell
    assert 'enterprise_benchmark_views' in enterprise_shell
    assert 'migration_verification_toolkit' in enterprise_shell
    assert 'economics_v2' in enterprise_shell

    foundation_nav = build_nav_for_user(
        cfg=ia_cfg,
        role=role,
        permissions=perms,
        enabled_features=foundation.enabled_features,
        enabled_modules=foundation.enabled_modules,
    )
    nav_keys = {item.key for group in foundation_nav for item in group.items}
    assert 'economics_v2' not in nav_keys
    assert 'ai_assistant' not in nav_keys


def test_t30_04_packaging_summary_page_docs_and_config_gates_are_present() -> None:
    cfg = load_commercial_packaging_config()
    assert cfg['editions']['foundation']['label'] == 'Foundation'
    assert 'economics' in cfg['module_catalog']
    assert 'enterprise_default' in cfg['runtime_profiles']

    summary = build_packaging_summary(project_root='.')
    assert summary['runtime']['edition_key'] == 'enterprise'
    assert summary['license_unit'] == 'site'
    md = render_packaging_markdown(summary)
    assert '# Commercial packaging' in md
    assert 'Enabled modules' in md
    assert 'implementation_scope_unit' in md

    widget = Path('streamlit_app/commercial_packaging.py').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/72_Commercial_Packaging_And_Editions.py').read_text(encoding='utf-8')
    docs = Path('docs/commercial_packaging_and_editions.md').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    project_map = Path('docs/project_map.md').read_text(encoding='utf-8')
    pytest_gate = Path('ci/pytest_gate.txt').read_text(encoding='utf-8')

    assert 'render_commercial_packaging_widget' in widget
    assert 'Commercial packaging и editions' in page
    assert 'commercial_packaging_and_editions' in ia
    assert 'pages/72_Commercial_Packaging_And_Editions.py' in ia
    assert 'edition/feature model' in docs
    assert 'config gates' in docs
    assert 'technical flags/configs' in docs
    assert '## T30-04 — Commercial packaging и edition model' in assumptions
    assert 'docs/commercial_packaging_and_editions.md' in readme
    assert 'commercial packaging' in project_map.lower()
    assert 'tests/test_t30_04_commercial_packaging_and_editions.py' in pytest_gate
