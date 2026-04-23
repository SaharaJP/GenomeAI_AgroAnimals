from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.report_to_action_bridge import build_report_bridge_snapshot, normalize_report_bridge_team
from core.workflow import get_decision
from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.report_to_action_bridge import (
    create_report_bridge_decision,
    create_report_bridge_worklist,
)
from core.infra.web_db import init_db


@dataclass
class _Ctx:
    artifacts_dir: Path
    web_storage_dir: Path


def _user(*perms: str) -> dict[str, object]:
    return {
        'id': 7,
        'username': 'coordinator',
        'role': 'Admin',
        'tenant_id': 'default',
        'permissions': list(perms),
        'request_id': 'REQ-T24-05',
    }


def test_t24_05_build_report_bridge_snapshot_extracts_rows_and_sections() -> None:
    snapshot = build_report_bridge_snapshot(
        report_ref={
            'data_version': 'dv_t24_05',
            'qc_run': 'qc_t24_05',
            'model_version': 'mdl_t24_05',
            'scoring_run': 'score_t24_05',
            'report_version': 'report_t24_05',
        },
        toc=[
            {'level': 1, 'title': 'QC', 'anchor': 'qc'},
            {'level': 1, 'title': 'Recommendations', 'anchor': 'recommendations'},
        ],
        fact_pack={
            'top_lists': {
                'priority': [
                    {
                        'animal_id': 'A-101',
                        'farm_id': 'F-1',
                        'action': 'PRIORITY',
                        'confidence': 'HIGH',
                        'action_reasons': 'high_index',
                    }
                ]
            },
            'productivity_explainability': {
                'animal_explainability': [
                    {
                        'animal_id': 'A-102',
                        'prediction': 10450.0,
                        'confidence': 'MEDIUM',
                        'explain_top_factors_text': 'parity, calving_year',
                    }
                ]
            },
            'qc': {'qc_status': 'WARN'},
            'ml': {'metrics': {'mae': 123.4, 'rmse': 234.5}},
            'scoring': {'row_counts': {'n_priority': 1, 'n_observe': 2}},
        },
    )
    assert snapshot['summary']['row_contexts_n'] >= 2
    assert snapshot['summary']['section_contexts_n'] == 2
    row = snapshot['actionable_rows'][0]
    assert row['object_type'] == 'animal'
    assert row['object_id'].startswith('A-')
    linked_types = {str(x['object_type']) for x in row['linked_objects']}
    assert {'animal', 'report_version', 'data_version'}.issubset(linked_types)
    facts = {str(x['fact']) for x in row['source_facts']}
    assert {'data_version', 'report_version', 'action', 'confidence'}.issubset(facts)


def test_t24_05_normalize_team_alias_supports_practical_operator_terms() -> None:
    assert normalize_report_bridge_team('zootech') == 'team-repro'
    assert normalize_report_bridge_team('vet') == 'team-health'
    assert normalize_report_bridge_team('team-qc') == 'team-qc'


def test_t24_05_create_decision_from_report_preserves_bridge_metadata_and_audit(tmp_path: Path) -> None:
    ctx = _Ctx(artifacts_dir=tmp_path / 'artifacts', web_storage_dir=tmp_path / 'web_storage')
    ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)
    ctx.web_storage_dir.mkdir(parents=True, exist_ok=True)
    user = _user('decisions.write', 'decisionlog.write')
    context = {
        'context_id': 'ctx-row-1',
        'context_kind': 'row',
        'section': 'priority',
        'source_path': 'top_lists.priority[0]',
        'object_type': 'animal',
        'object_id': 'A-201',
        'source_facts': [{'fact': 'confidence', 'value': 'HIGH'}],
        'linked_objects': [{'object_type': 'animal', 'object_id': 'A-201'}],
    }
    report_ref = {
        'data_version': 'dv_t24_05',
        'qc_run': 'qc_t24_05',
        'model_version': 'mdl_t24_05',
        'scoring_run': 'score_t24_05',
        'report_version': 'report_t24_05',
    }
    res = create_report_bridge_decision(
        ctx,
        user=user,
        context=context,
        action='accept',
        reason='FOLLOW_UP',
        comment='Создано из отчёта',
        report_ref=report_ref,
    )
    assert res.ok is True
    decision_id = str((res.payload or {}).get('decision_id') or '')
    with connect_web_db(ctx) as conn:
        stored = get_decision(conn, tenant_id='default', decision_id=decision_id)
        assert stored is not None
        assert stored['report_version'] == 'report_t24_05'
        assert stored['data_version'] == 'dv_t24_05'
        metadata = dict(stored.get('metadata') or {})
        assert metadata['report_context_id'] == 'ctx-row-1'
        assert metadata['context_kind'] == 'row'
        assert metadata['section'] == 'priority'
        actions = {str(row[0]) for row in conn.execute("SELECT action FROM audit_log").fetchall()}
        assert 'report.bridge.decision.create' in actions


def test_t24_05_create_worklist_from_report_preserves_versions_source_facts_and_audit(tmp_path: Path) -> None:
    ctx = _Ctx(artifacts_dir=tmp_path / 'artifacts', web_storage_dir=tmp_path / 'web_storage')
    ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)
    ctx.web_storage_dir.mkdir(parents=True, exist_ok=True)
    user = _user('tasks.write')
    context = {
        'context_id': 'ctx-row-2',
        'context_kind': 'row',
        'section': 'health_attention',
        'source_path': 'top_lists.health_attention[0]',
        'object_type': 'animal',
        'object_id': 'A-301',
        'source_facts': [{'fact': 'scc_cells_ml', 'value': '450000'}],
        'linked_objects': [{'object_type': 'animal', 'object_id': 'A-301'}],
    }
    report_ref = {
        'data_version': 'dv_t24_05',
        'qc_run': 'qc_t24_05',
        'model_version': 'mdl_t24_05',
        'scoring_run': 'score_t24_05',
        'report_version': 'report_t24_05',
    }
    res = create_report_bridge_worklist(
        ctx,
        user=user,
        context=context,
        worklist_type='health_follow_up',
        title='Проверить животное из отчёта',
        priority=2,
        due_at='2026-04-03T10:00:00+00:00',
        assignee_team='zootech',
        confidence=0.8,
        note='Bridge follow-up',
        report_ref=report_ref,
    )
    worklist = dict(res['worklist'])
    assert str(res['worklist_id']).strip()
    assert worklist['report_version'] == 'report_t24_05'
    assert worklist['data_version'] == 'dv_t24_05'
    assert worklist['assignee_team'] == 'team-repro'
    assert (worklist.get('linked_source_facts') or [])[0]['fact'] == 'scc_cells_ml'
    why = dict(worklist.get('why') or {})
    assert why['report_context_id'] == 'ctx-row-2'
    with connect_web_db(ctx) as conn:
        actions = {str(row[0]) for row in conn.execute("SELECT action FROM audit_log").fetchall()}
        assert 'report.bridge.worklist.create' in actions
        assert 'worklist.create' in actions


def test_t24_05_report_view_references_bridge_layer_and_actions() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_view = (repo_root / 'streamlit_app' / 'pages' / '16_Report_View.py').read_text(encoding='utf-8')
    bridge_doc = (repo_root / 'docs' / 'report_to_action_bridge.md').read_text(encoding='utf-8')
    assert 'load_report_bridge_snapshot' in report_view
    assert 'Create decision from report' in report_view
    assert 'Create worklist from report' in report_view
    assert 'Report-to-action bridge' in bridge_doc
