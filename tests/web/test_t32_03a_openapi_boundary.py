from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from packages.contracts.canonical_api_contracts import (
    CANONICAL_OPENAPI_PATH,
    CANONICAL_REQUIRED_PATHS,
    build_canonical_openapi_spec,
    load_json,
)


@pytest.fixture()
def canonical_app(tmp_path: Path):
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
    return appmod.app


def test_t32_03a_canonical_openapi_snapshot_matches_generated(canonical_app) -> None:
    generated = build_canonical_openapi_spec(app=canonical_app)
    snapshot = load_json(CANONICAL_OPENAPI_PATH)
    assert generated == snapshot


def test_t32_03a_canonical_openapi_contains_required_paths_and_contract_models(canonical_app) -> None:
    spec = build_canonical_openapi_spec(app=canonical_app)
    assert sorted(spec['paths']) == sorted(CANONICAL_REQUIRED_PATHS)
    schemas = spec['components']['schemas']
    assert 'AuthLoginResponse' in schemas
    assert 'AlertsListResponse' in schemas
    assert 'DecisionIntelligenceResponse' in schemas
    assert 'PilotResponse' in schemas
    assert 'ReadinessResponse' in schemas


def _login_admin(client: TestClient) -> None:
    r = client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_t32_03a_boundary_supports_decision_intelligence_pilot_and_readiness(canonical_app, tmp_path: Path) -> None:
    with TestClient(canonical_app) as client:
        _login_admin(client)

        r_di = client.get('/api/app/v1/decision-intelligence')
        assert r_di.status_code == 200, r_di.text
        body_di = r_di.json()
        assert body_di['schema'] == 'genomeai.api.decision_intelligence.summary.v1'
        assert 'summary' in body_di and 'top_actions' in body_di

        r_pilot = client.get('/api/app/v1/pilot')
        assert r_pilot.status_code == 200, r_pilot.text
        body_pilot = r_pilot.json()
        assert body_pilot['schema'] == 'genomeai.api.pilot.summary.v1'
        assert 'summary' in body_pilot and 'items' in body_pilot

        r_readiness = client.get('/api/app/v1/readiness')
        assert r_readiness.status_code == 200, r_readiness.text
        body_readiness = r_readiness.json()
        assert body_readiness['schema'] == 'genomeai.api.readiness.summary.v1'
        assert 'summary' in body_readiness and 'checks' in body_readiness
