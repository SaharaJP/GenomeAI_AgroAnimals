"""P1-6 integration health providers.

Importing this module registers all bundled providers with the registry
in `core.interoperability.integrations_health`. The aggregator endpoint
triggers this import on first call.
"""
from core.interoperability.integrations_health import register_provider
from core.interoperability.providers.connectors_v1 import ConnectorsV1HealthProvider
from core.interoperability.providers.iot_stubs import (
    IoTStubsHealthProvider,
    SensorIngestionStubProvider,
)
from core.interoperability.providers.llm import LLMHealthProvider
from core.interoperability.providers.ru_stubs import RuExternalSystemsStubProvider


def register_bundled_providers() -> None:
    register_provider(LLMHealthProvider())
    register_provider(ConnectorsV1HealthProvider())
    register_provider(IoTStubsHealthProvider())
    register_provider(SensorIngestionStubProvider())
    register_provider(RuExternalSystemsStubProvider())


register_bundled_providers()


__all__ = ['register_bundled_providers']
