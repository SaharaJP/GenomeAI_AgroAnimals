from __future__ import annotations

from packages.contracts.api_boundary_v1 import (
    AlertsListResponse,
    AssistantResolveTargetResponse,
    ProfileResponse,
    ReportsListResponse,
)


def test_t32_02_contract_models_accept_expected_payloads() -> None:
    alerts = AlertsListResponse(total=1, limit=20, offset=0, items=[])
    assert alerts.schema == 'genomeai.api.alerts.list.v1'

    reports = ReportsListResponse(total=1, items=[])
    assert reports.schema == 'genomeai.api.reports.list.v1'

    profile = ProfileResponse(entity={'object_type': 'animal', 'object_id': 'A-1'}, summary={'alerts_open': 1}, alerts=[], worklists=[], decisions=[])
    assert profile.entity.object_id == 'A-1'
    assert profile.summary.alerts_open == 1

    assistant = AssistantResolveTargetResponse(target={'data_version': 'dv1'}, resolution_summary='ok')
    assert assistant.target['data_version'] == 'dv1'
    assert assistant.schema == 'genomeai.api.assistant.resolve_target.v1'
