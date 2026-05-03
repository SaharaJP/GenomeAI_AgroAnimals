from __future__ import annotations

from pathlib import Path

from core.explainability_by_object import (
    build_alert_explainability,
    build_economics_delta_explainability,
    build_group_explainability,
    build_report_explainability,
    build_worklist_explainability,
)


def test_t29_04_worklist_bundle_keeps_versions_facts_thresholds_and_linkage() -> None:
    worklist = {
        'worklist_id': 'wl-1',
        'title': 'Check transition cow',
        'object_type': 'animal',
        'object_id': 'A-100',
        'related_alert': 'al-9',
        'farm_id': 'farm-1',
        'site_id': 'site-1',
        'group_id': 'grp-1',
        'priority': 'P1',
        'status': 'open',
        'stage': 'triage',
        'due_bucket': 'today',
        'confidence': 0.82,
        'expected_effect': 'Inspect today to reduce transition loss.',
        'linked_facts_preview': ['milk_7d_avg dropped', 'fresh cow risk flag'],
        'why': {
            'reason': 'fresh transition risk',
            'priority_threshold': 'P1 if risk>=0.7',
            'model_factor_top': 'dim_7 and milk_7d_avg',
        },
        'physical_location': 'farm-1 / site-1 / pen-7',
        'organizational_location': 'team-fresh / day',
        'lineage_path': 'farm-1 > site-1 > grp-1 > pen-7',
        'data_version': 'dv1',
        'qc_run': 'qc1',
        'model_version': 'mv1',
        'scoring_run': 'sv1',
        'report_version': 'rv1',
    }
    economics = {
        'why_now': 'Delay adds cost of delay.',
        'factors': [{'factor': 'expected_gain_rub', 'value': '1200', 'source_linkage': 'economics.expected_gain_rub'}],
        'quality_caveats': ['bounded heuristic'],
    }

    bundle = build_worklist_explainability(worklist=worklist, economics_snapshot=economics)
    assert bundle.context_kind == 'worklist'
    assert bundle.source_linkage['data_version'] == 'dv1'
    assert any(r['value'] == 'fresh cow risk flag' for r in bundle.source_facts)
    assert any(r['label'] == 'priority_threshold' for r in bundle.thresholds)
    assert any('dim_7' in r['value'] for r in bundle.model_factors)
    assert any(r['kind'] == 'animal' and r['id'] == 'A-100' for r in bundle.linked_objects)
    assert any(r['label'] == 'caveat 1' or r['label'].startswith('quality_caveats') for r in bundle.caveats)


def test_t29_04_alert_bundle_does_not_invent_model_factors() -> None:
    alert = {
        'alert_id': 'al-1',
        'title': 'Milk quality alert',
        'alert_type': 'SCC_HIGH',
        'object_type': 'group',
        'object_id': 'pen-2',
        'cause': 'SCC above threshold',
        'confidence': 0.58,
        'data_version': 'dv2',
    }
    facts = [{'label': 'latest_scc_cells_ml', 'value': '410000', 'source': 'lab', 'source_linkage': 'lab.latest_scc_cells_ml'}]
    bundle = build_alert_explainability(alert=alert, source_facts=facts, bundle={'facts': facts})
    assert bundle.context_kind == 'alert'
    assert any(r['value'] == 'SCC above threshold' for r in bundle.source_facts)
    assert any(r['value'] == '410000' for r in bundle.source_facts)
    assert bundle.model_factors == []
    assert any('low-confidence' in r['value'] for r in bundle.caveats)


def test_t29_04_report_group_and_economics_bundles_are_consistent() -> None:
    report_bundle = build_report_explainability(
        data_version='dv3',
        report_version='rv3',
        selected_row={'kind_label': 'Executive', 'approval_status': 'approved'},
        dashboard_summary={'summary_text': 'Milk quality worsened', 'lineage': {'qc_run': 'qc3', 'model_version': 'mv3'}},
        source_facts=[{'label': 'coverage', 'value': '92%', 'source': 'fact_pack', 'source_linkage': 'fact_pack.coverage'}],
        related_objects=[{'kind': 'alert', 'id': 'al-3', 'source_linkage': 'alert:al-3'}],
        approval_status='approved',
    )
    assert report_bundle.context_kind == 'report'
    assert report_bundle.source_linkage['report_version'] == 'rv3'
    assert any(r['value'] == '92%' for r in report_bundle.source_facts)
    assert any(r['label'] == 'status' and r['value'] == 'approved' for r in report_bundle.thresholds)

    group_bundle = build_group_explainability(
        pen_id='pen-9',
        data_version='dv4',
        group_hub={'group_status': {'label': 'needs_action', 'hint': 'Two cows need attention'}, 'recent_events': [{'label': 'recent_event', 'value': 'mastitis check', 'source': 'event'}]},
        alerts=[{'alert_id': 'al-4', 'cause': 'mastitis risk'}],
        tasks=[{'task_id': 't-4'}],
        decisions=[{'decision_id': 'd-4', 'action': 'review'}],
        location_info={'physical_location': 'farm-1 / site-2 / pen-9', 'organizational_location': 'team-health', 'lineage_path': 'farm-1 > site-2 > pen-9'},
    )
    assert group_bundle.context_kind == 'group'
    assert any(r['value'] == 'mastitis risk' for r in group_bundle.source_facts)
    assert any(r['kind'] == 'task' and r['id'] == 't-4' for r in group_bundle.linked_objects)

    econ_bundle = build_economics_delta_explainability(snapshot={
        'title': 'Economics delta on culling review',
        'worklist_id': 'wl-9',
        'object_type': 'animal',
        'object_id': 'A-9',
        'why_now': 'Margin drops if action is deferred.',
        'data_version': 'dv5',
        'linked_source_facts': [{'label': 'milk_loss_rub', 'value': '450', 'source': 'economics', 'source_linkage': 'economics.milk_loss_rub'}],
        'factors': [{'factor': 'expected_gain_rub', 'value': '1400', 'source_linkage': 'economics.expected_gain_rub'}],
        'quality_caveats': ['uses bounded heuristic'],
    })
    assert econ_bundle.context_kind == 'economics_delta'
    assert any(r['value'] == '450' for r in econ_bundle.source_facts)
    assert any(r['value'] == '1400' for r in econ_bundle.events + econ_bundle.model_factors)
    assert any('heuristic' in r['value'] for r in econ_bundle.caveats)


def test_t29_04_cross_page_integration_and_docs_exist() -> None:
    root = Path('.')
    helper = (root / 'streamlit_app' / 'explainability_by_object.py').read_text(encoding='utf-8')
    assert 'render_explainability_panel' in helper

    for rel in [
        'streamlit_app/pages/43_Daily_Worklists_By_Role.py',
        'streamlit_app/pages/44_Operational_Planner.py',
        'streamlit_app/pages/5_Alert_Center_v2.py',
        'streamlit_app/pages/14_Group_Profile.py',
        'streamlit_app/pages/15_Animal_Profile.py',
        'streamlit_app/pages/16_Report_View.py',
        'streamlit_app/pages/65_Economics_Per_Action.py',
    ]:
        text = (root / rel).read_text(encoding='utf-8')
        assert 'render_explainability_panel' in text

    doc = (root / 'docs' / 'explainability_by_object.md').read_text(encoding='utf-8')
    assert 'why this cow / why this list / why this alert / why this economics delta' in doc
    assert 'source linkage' in doc.lower()
