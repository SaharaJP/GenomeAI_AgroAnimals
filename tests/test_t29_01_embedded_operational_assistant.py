from __future__ import annotations

from pathlib import Path

from core.assistant import build_assistant_answer_linkage, build_embedded_assistant_actions, filter_embedded_assistant_actions
from streamlit_app.assistant_feedback_ux import build_contextual_prompts


def test_t29_01_builds_linkage_and_worklist_actions() -> None:
    linkage = build_assistant_answer_linkage(
        context_kind='worklist',
        object_type='animal',
        object_id='A-101',
        farm_id='F-1',
        group_id='G-1',
        related_alert='AL-7',
        worklist_id='WL-9',
        task_id='TSK-2',
        data_version='dv_demo',
        qc_run='qc_001',
        model_version='mdl_001',
        scoring_run='scr_001',
        report_version='rep_001',
    ).to_dict()
    assert linkage['context_kind'] == 'worklist'
    assert linkage['object_type'] == 'animal'
    assert linkage['object_id'] == 'A-101'
    assert linkage['worklist_id'] == 'WL-9'
    assert linkage['report_version'] == 'rep_001'

    actions = build_embedded_assistant_actions(
        context_kind='worklist',
        object_type='animal',
        object_id='A-101',
        related_alert='AL-7',
        worklist_id='WL-9',
        worklist_type='vet',
        farm_id='F-1',
    )
    keys = {a.key for a in actions}
    labels = {a.label for a in actions}
    assert 'open_animal_profile' in keys
    assert 'open_alert_center' in keys
    assert 'open_economics_per_action' in keys
    assert 'open_operational_what_if' in keys
    assert 'worklist_note' in keys
    assert 'Открыть animal profile' in labels
    assert any(a.kind == 'decision_note' and a.decision_action == 'assistant.triage.note' for a in actions)


def test_t29_01_filters_actions_by_permission_and_supports_planner() -> None:
    actions = build_embedded_assistant_actions(
        context_kind='planner_item',
        object_type='group',
        object_id='PEN-1',
        worklist_id='WL-77',
        farm_id='F-2',
    )
    visible = filter_embedded_assistant_actions(actions, effective_permissions=['tasks.view'])
    keys = {a.key for a in visible}
    assert 'open_group_profile' in keys
    assert 'open_daily_worklists' in keys
    assert 'open_tasks_workflow' in keys
    assert 'planner_note' not in keys

    visible_with_decision = filter_embedded_assistant_actions(actions, effective_permissions=['tasks.view', 'decisionlog.write'])
    assert 'planner_note' in {a.key for a in visible_with_decision}


def test_t29_01_prompts_docs_and_page_wiring_are_present() -> None:
    root = Path(__file__).resolve().parents[1]
    prompts_worklist = [p.key for p in build_contextual_prompts('worklist')]
    prompts_planner = [p.key for p in build_contextual_prompts('planner_item')]
    assert prompts_worklist == ['why_queue', 'triage', 'execution']
    assert prompts_planner == ['why_bucket', 'next_step', 'handover']

    helper = (root / 'streamlit_app' / 'assistant_feedback_ux.py').read_text(encoding='utf-8')
    worklists_page = (root / 'streamlit_app' / 'pages' / '43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    planner_page = (root / 'streamlit_app' / 'pages' / '44_Operational_Planner.py').read_text(encoding='utf-8')
    home_page = (root / 'streamlit_app' / 'home_v3.py').read_text(encoding='utf-8')
    alert_page = (root / 'streamlit_app' / 'pages' / '5_Alert_Center_v2.py').read_text(encoding='utf-8')
    animal_page = (root / 'streamlit_app' / 'pages' / '15_Animal_Profile.py').read_text(encoding='utf-8')
    group_page = (root / 'streamlit_app' / 'pages' / '14_Group_Profile.py').read_text(encoding='utf-8')
    report_page = (root / 'streamlit_app' / 'pages' / '16_Report_View.py').read_text(encoding='utf-8')
    core_helper = (root / 'src' / 'core' / 'assistant' / 'embedded_operational.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'embedded_operational_assistant.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')

    assert 'Помощник в operational-контексте' in helper
    assert '_render_embedded_operational_actions' in helper
    assert 'assistant.contextual.linked_action' in helper
    assert 'context_kind="worklist"' in worklists_page
    assert 'context_kind="planner_item"' in planner_page
    assert 'render_contextual_assistant_panel(' in home_page
    assert 'render_contextual_assistant_panel(' in alert_page
    assert 'render_contextual_assistant_panel(' in animal_page
    assert 'render_contextual_assistant_panel(' in group_page
    assert 'render_contextual_assistant_panel(' in report_page
    assert 'build_embedded_assistant_actions' in core_helper
    assert 'assistant.triage.note' in core_helper
    assert 'linked actions' in docs.lower()
    assert 'fact-pack only' in docs.lower()
    assert '## T29-01 — embedded operational assistant' in assumptions
