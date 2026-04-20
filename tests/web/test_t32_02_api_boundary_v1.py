from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / 'web_storage'
    artifacts = tmp_path / 'artifacts'
    os.environ['GENOMEAI_PROJECT_ROOT'] = str(repo_root)
    os.environ['GENOMEAI_WEB_STORAGE'] = str(storage)
    os.environ['GENOMEAI_ARTIFACTS_ROOT'] = str(artifacts)
    os.environ['GENOMEAI_WEB_DISABLE_WORKER'] = '1'
    os.environ['GENOMEAI_WEB_SECRET'] = 'test-secret'

    import web_cabinet.app as appmod

    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c, artifacts, appmod


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_api_boundary_v1_daily_use_contracts(client) -> None:
    c, artifacts, _appmod = client
    _login(c, 'admin', 'admin')

    dv = 'dv_boundary'
    rv = 'rv_boundary_001'
    (artifacts / dv / 'reports' / rv).mkdir(parents=True, exist_ok=True)

    alert_payload = {
        'alert_type': 'health_risk',
        'title': 'Проверить животное A-100',
        'source': 'pytest',
        'cause': 'Synthetic high-risk flag',
        'confidence': 0.82,
        'object_type': 'animal',
        'object_id': 'A-100',
        'what_to_do': [{'action': 'inspect', 'label': 'Осмотреть'}],
        'why': {'rule': 'pytest'},
        'data_version': dv,
        'report_version': rv,
    }
    r_alert = c.post('/api/alerts_v2', json=alert_payload)
    assert r_alert.status_code == 200, r_alert.text
    alert_id = r_alert.json()['alert_id']

    task_payload = {
        'task_type': 'animal.check',
        'title': 'Осмотреть A-100',
        'domain': 'health',
        'priority': 2,
        'object_type': 'animal',
        'object_id': 'A-100',
        'related_alert': alert_id,
        'assignee_team': 'team-health',
        'what_to_do': [{'action': 'inspect'}],
        'why': {'source': 'pytest'},
        'data_version': dv,
        'report_version': rv,
    }
    r_task = c.post('/api/tasks_v1', json=task_payload)
    assert r_task.status_code == 200, r_task.text
    task_id = r_task.json()['task_id']

    decision_payload = {
        'action': 'animal.inspect.requested',
        'object_type': 'animal',
        'object_id': 'A-100',
        'related_alert': alert_id,
        'comment': 'Created from boundary test',
        'data_version': dv,
        'report_version': rv,
    }
    r_decision = c.post('/api/decision_log_v2', json=decision_payload)
    assert r_decision.status_code == 200, r_decision.text

    feedback_payload = {
        'recommendation_id': 'rec:boundary:test:A-100',
        'decision': 'accepted',
        'reason_code': 'CONFIRMED_BY_SPECIALIST',
        'comment': 'ok',
        'related_alert': alert_id,
        'task_id': task_id,
        'object_type': 'animal',
        'object_id': 'A-100',
        'data_version': dv,
        'report_version': rv,
        'scoring_run': 'sr_boundary',
        'recommendation_created_at': '2026-04-10T08:00:00Z',
        'feedback_source': 'assistant',
        'metadata': {'source': 'pytest'},
    }
    r_feedback = c.post('/api/feedback_v1', json=feedback_payload)
    assert r_feedback.status_code == 200, r_feedback.text

    weekly_plan_payload = {
        'name': 'Weekly Ops',
        'week_start': '2026-04-13',
        'summary': 'Synthetic planner item',
        'farm_id': 'F-1',
        'data_version': dv,
        'action_items': [{'title': 'Inspect A-100', 'object_type': 'animal', 'object_id': 'A-100'}],
    }
    r_plan = c.post('/api/weekly_plans_v1', json=weekly_plan_payload)
    assert r_plan.status_code == 200, r_plan.text

    scenario_payload = {
        'name': 'Economics Scenario',
        'description': 'Synthetic what-if',
        'data_version': dv,
        'params': {'milk_price_delta_pct': 5},
    }
    r_scenario = c.post('/api/whatif_scenarios_v1', json=scenario_payload)
    assert r_scenario.status_code == 200, r_scenario.text

    r_boundary_alerts = c.get('/api/app/v1/alerts', params={'object_type': 'animal', 'object_id': 'A-100'})
    assert r_boundary_alerts.status_code == 200, r_boundary_alerts.text
    alerts_body = r_boundary_alerts.json()
    assert alerts_body['schema'] == 'genomeai.api.alerts.list.v1'
    assert alerts_body['total'] >= 1
    assert alerts_body['items'][0]['entity']['object_id'] == 'A-100'

    r_boundary_worklists = c.get('/api/app/v1/worklists', params={'object_type': 'animal', 'object_id': 'A-100'})
    assert r_boundary_worklists.status_code == 200, r_boundary_worklists.text
    worklists_body = r_boundary_worklists.json()
    assert worklists_body['schema'] == 'genomeai.api.worklists.list.v1'
    assert worklists_body['items'][0]['entity']['object_type'] == 'animal'

    r_profile = c.get('/api/app/v1/profiles/animal/A-100')
    assert r_profile.status_code == 200, r_profile.text
    profile_body = r_profile.json()
    assert profile_body['schema'] == 'genomeai.api.profile.v1'
    assert profile_body['entity']['object_id'] == 'A-100'
    assert profile_body['summary']['alerts_open'] >= 1
    assert profile_body['summary']['worklists_open'] >= 1
    assert profile_body['summary']['decisions_total'] >= 1

    r_planner = c.get('/api/app/v1/planner')
    assert r_planner.status_code == 200, r_planner.text
    planner_body = r_planner.json()
    assert planner_body['schema'] == 'genomeai.api.planner.v1'
    assert planner_body['pending_approvals'] >= 0
    assert isinstance(planner_body['weekly_plans'], list)

    r_reports = c.get('/api/app/v1/reports', params={'data_version': dv})
    assert r_reports.status_code == 200, r_reports.text
    reports_body = r_reports.json()
    assert reports_body['schema'] == 'genomeai.api.reports.list.v1'
    assert any(item['report_version'] == rv for item in reports_body['items'])

    r_decisions = c.get('/api/app/v1/decisions', params={'object_type': 'animal', 'object_id': 'A-100'})
    assert r_decisions.status_code == 200, r_decisions.text
    decisions_body = r_decisions.json()
    assert decisions_body['schema'] == 'genomeai.api.decisions.list.v1'
    assert decisions_body['total'] >= 1

    r_feedback_boundary = c.get('/api/app/v1/feedback', params={'object_type': 'animal', 'object_id': 'A-100'})
    assert r_feedback_boundary.status_code == 200, r_feedback_boundary.text
    feedback_body = r_feedback_boundary.json()
    assert feedback_body['schema'] == 'genomeai.api.feedback.list.v1'
    assert feedback_body['total'] >= 1
    assert feedback_body['metrics']['total_feedback'] >= 1

    r_economics = c.get('/api/app/v1/economics')
    assert r_economics.status_code == 200, r_economics.text
    economics_body = r_economics.json()
    assert economics_body['schema'] == 'genomeai.api.economics.list.v1'
    assert economics_body['scenarios_total'] >= 1

    r_support = c.get('/api/app/v1/support')
    assert r_support.status_code == 200, r_support.text
    support_body = r_support.json()
    assert support_body['schema'] == 'genomeai.api.support.summary.v1'
    assert 'release' in support_body
    assert 'observability' in support_body


def test_api_boundary_v1_assistant_resolve_target_contract(client, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _artifacts, _appmod = client
    _login(c, 'admin', 'admin')

    import web_cabinet.api_boundary_v1 as boundary_mod

    monkeypatch.setattr(boundary_mod, 'build_fact_pack_for_assistant', lambda **kwargs: {'schema': 'fake'})
    monkeypatch.setattr(
        boundary_mod,
        'resolve_copilot_target_from_fact_pack',
        lambda fact_pack, target: {
            'target': dict(target),
            'fact': {'fact_id': 'f1', 'value': 123},
            'table': {'table_id': 't1', 'rows': 1},
            'sources': [{'source_id': 'src1', 'ref': 'artifacts/dv_demo/report.json', 'section': 'alerts'}],
            'missing_data_request': {},
        },
    )
    monkeypatch.setattr(boundary_mod, 'build_copilot_navigation_hints', lambda target, resolution: [{'kind': 'open_alerts'}])
    monkeypatch.setattr(boundary_mod, 'build_copilot_detail_actions', lambda target, resolution: [{'action': 'open_detail'}])
    monkeypatch.setattr(boundary_mod, 'summarize_target_resolution', lambda resolution: 'Synthetic resolution summary')

    r = c.post(
        '/api/app/v1/assistant/resolve-target',
        json={'data_version': 'dv_demo', 'section': 'alerts', 'metric': 'high_risk_count'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['schema'] == 'genomeai.api.assistant.resolve_target.v1'
    assert body['resolution_summary'] == 'Synthetic resolution summary'
    assert body['target']['data_version'] == 'dv_demo'
    assert body['fact']['fact_id'] == 'f1'
    assert body['detail_actions'][0]['action'] == 'open_detail'
