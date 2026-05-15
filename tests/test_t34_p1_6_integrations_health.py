"""P1-6 unit tests: integration health aggregator.

These run as plain unit tests (no FastAPI / DB) — registry-level only.
End-to-end HTTP smoke lives in artifacts/_ci/p1_6_smoke.log.
"""
from __future__ import annotations

import pytest


class _FakeConn:
    """Minimal stand-in for a DB connection used by providers."""

    def execute(self, *_args, **_kwargs):
        class _Cursor:
            def fetchall(self_inner):
                return []

            def fetchone(self_inner):
                return None

        return _Cursor()

    def rollback(self):
        return None


def _reset_and_register():
    from core.interoperability.integrations_health import register_provider, reset_registry
    from core.interoperability.providers.iot_stubs import IoTStubsHealthProvider, SensorIngestionStubProvider
    from core.interoperability.providers.llm import LLMHealthProvider
    from core.interoperability.providers.ru_stubs import RuExternalSystemsStubProvider

    reset_registry()
    register_provider(LLMHealthProvider())
    register_provider(IoTStubsHealthProvider())
    register_provider(SensorIngestionStubProvider())
    register_provider(RuExternalSystemsStubProvider())


def test_contract_round_trip():
    from packages.contracts.integrations_health_v1 import IntegrationHealth, IntegrationsHealthResponse

    item = IntegrationHealth(id='llm.openai', name='LLM', kind='llm', status='ok')
    resp = IntegrationsHealthResponse(items=[item], total=1)
    dumped = resp.model_dump(by_alias=True)
    assert dumped['schema'] == 'genomeai.api.integrations.health.v1'
    assert dumped['items'][0]['kind'] == 'llm'
    assert dumped['total'] == 1


def test_iot_stubs_return_six_disabled_rows():
    from core.interoperability.providers.iot_stubs import IoTStubsHealthProvider

    rows = IoTStubsHealthProvider().get_health(_FakeConn())
    assert len(rows) == 6
    ids = {r.id for r in rows}
    assert {'iot.collar', 'iot.bolus', 'iot.ear_tag', 'iot.leg_band', 'iot.smart_scale', 'iot.camera'} <= ids
    assert all(r.status == 'disabled' and r.kind == 'iot_device' for r in rows)


def test_ru_stubs_return_herriot_disabled():
    from core.interoperability.providers.ru_stubs import RuExternalSystemsStubProvider

    rows = RuExternalSystemsStubProvider().get_health(_FakeConn())
    assert len(rows) == 1
    assert rows[0].id == 'external.herriot'
    assert rows[0].status == 'disabled'
    assert 'P2-4' in (rows[0].note or '')


def test_sensor_ingestion_stub_present():
    from core.interoperability.providers.iot_stubs import SensorIngestionStubProvider

    rows = SensorIngestionStubProvider().get_health(_FakeConn())
    assert len(rows) == 1
    assert rows[0].id == 'sensor.ingestion_api'
    assert rows[0].status == 'disabled'


def test_llm_provider_reflects_env(monkeypatch):
    from core.interoperability.providers.llm import LLMHealthProvider

    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY_FILE', raising=False)
    rows = LLMHealthProvider().get_health(_FakeConn())
    assert len(rows) == 1
    assert rows[0].status == 'disabled'

    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    rows2 = LLMHealthProvider().get_health(_FakeConn())
    assert rows2[0].status == 'ok'


def test_collect_health_isolates_provider_failures():
    """If one provider raises, the aggregator emits a synthetic down-row
    and continues with other providers."""
    from core.interoperability.integrations_health import (
        collect_health,
        register_provider,
        reset_registry,
    )
    from core.interoperability.providers.iot_stubs import IoTStubsHealthProvider

    class _BoomProvider:
        def get_health(self, conn):
            raise RuntimeError('boom!')

    reset_registry()
    register_provider(_BoomProvider())
    register_provider(IoTStubsHealthProvider())

    rows = collect_health(_FakeConn())
    # 1 synthetic down-row + 6 iot stubs
    assert len(rows) == 7
    err_row = next(r for r in rows if r.id.startswith('_error.'))
    assert err_row.status == 'down'
    assert 'boom' in (err_row.last_error or '')


def test_registry_is_idempotent():
    from core.interoperability.integrations_health import (
        iter_providers,
        register_provider,
        reset_registry,
    )
    from core.interoperability.providers.llm import LLMHealthProvider

    reset_registry()
    provider = LLMHealthProvider()
    register_provider(provider)
    register_provider(provider)
    assert len(iter_providers()) == 1
