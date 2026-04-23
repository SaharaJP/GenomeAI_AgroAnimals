from __future__ import annotations

from pathlib import Path

import core.security as rbac
from core.demo_farm import (
    build_demo_farm_dataset,
    build_role_demo_kit,
    build_role_demo_markdown,
    load_demo_farm_manifest,
    load_demo_scenarios_config,
)
from genomeai.target.validators_v2 import load_fixture_folder, validate_target_v2_relations
from streamlit_app.unified_shell import build_shell_for_user, load_shell_config


ROOT = Path(__file__).resolve().parents[1]


def test_t30_03_demo_dataset_build_is_synthetic_and_relation_clean(tmp_path: Path) -> None:
    out = tmp_path / 'demo_farm_v1'
    manifest = build_demo_farm_dataset(out)
    assert manifest['synthetic'] is True
    assert manifest['dataset_id'] == 'demo_farm_v1'
    assert set(manifest['farms']) == {'DEMO_FARM_001', 'DEMO_FARM_002'}
    assert 'DEMO_SITE_003' in set(manifest['sites'])

    dfs = load_fixture_folder(str(out))
    issues = validate_target_v2_relations(dfs)
    assert [i for i in issues if str(i.severity).upper() == 'ERROR'] == []
    assert (out / 'README_SYNTHETIC.md').exists()
    loaded = load_demo_farm_manifest(out)
    assert 'sales/pilot/UAT' in loaded['synthetic_note']


def test_t30_03_role_demo_kit_contains_benchmark_and_mobile_paths() -> None:
    cfg = load_demo_scenarios_config()
    shell_cfg = load_shell_config()
    dataset_dir = ROOT / 'data' / 'demo' / 'demo_farm_v1'
    build_demo_farm_dataset(dataset_dir)
    manifest = load_demo_farm_manifest(dataset_dir)

    director_sections = build_shell_for_user(
        cfg=shell_cfg,
        role=rbac.ROLE_DIRECTOR,
        permissions=set(rbac.DEFAULT_ROLE_PERMISSIONS.get(rbac.ROLE_DIRECTOR, [])),
        include_hidden=True,
    )
    director = build_role_demo_kit(role=rbac.ROLE_DIRECTOR, shell_sections=director_sections, cfg=cfg, manifest=manifest)
    scenario_ids = {s.scenario_id for s in director.scenarios}
    assert 'reports_and_brief' in scenario_ids
    assert 'economics_delta' in scenario_ids
    bench = [s for s in director.scenarios if s.benchmark_demo]
    assert bench, 'director demo should include benchmark scenario'
    assert any('68_Enterprise_Benchmark_Views.py' in step.page for s in director.scenarios for step in s.steps)

    operator_sections = build_shell_for_user(
        cfg=shell_cfg,
        role=rbac.ROLE_OPERATOR,
        permissions=set(rbac.DEFAULT_ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, [])),
        include_hidden=True,
    )
    operator = build_role_demo_kit(role=rbac.ROLE_OPERATOR, shell_sections=operator_sections, cfg=cfg, manifest=manifest)
    assert any('59_Cowside_Event_Entry.py' in step.page for s in operator.scenarios for step in s.steps)
    assert any('58_Mobile_Worklists.py' in step.page for s in operator.scenarios for step in s.steps)
    md = build_role_demo_markdown(operator)
    assert 'Synthetic note' in md and 'daily_operator_flow' in md


def test_t30_03_docs_page_and_scripts_are_wired() -> None:
    page = (ROOT / 'streamlit_app' / 'pages' / '71_Demo_Farm_And_Benchmark_Demos.py').read_text(encoding='utf-8')
    docs = (ROOT / 'docs' / 'demo_farm_and_benchmark_demos.md').read_text(encoding='utf-8')
    assumptions = (ROOT / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    ia = (ROOT / 'configs' / 'ui' / 'ia_v3.yaml').read_text(encoding='utf-8')
    assert 'Demo farm и benchmark demos' in page
    assert 'demo_farm_v1' in page
    assert 'Synthetic but realistic' in docs
    assert 'benchmark demos' in docs.lower()
    assert '## t30-03 — demo farm и benchmark demos' in assumptions.lower()
    assert 'pages/71_Demo_Farm_And_Benchmark_Demos.py' in ia
    assert (ROOT / 'scripts' / 'build_demo_farm_v1.py').exists()
    assert (ROOT / 'scripts' / 'smoke_t30_03_demo_farm.py').exists()
    assert (ROOT / 'scripts' / 'run_demo_farm_v1.sh').exists()
