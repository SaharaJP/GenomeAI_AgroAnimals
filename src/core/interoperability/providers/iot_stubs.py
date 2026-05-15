"""IoT device class stubs (P1-6 → upgraded in P2-3).

Six bounded device classes. Each is shown as `disabled` until P2-3
implements the actual ingest pipeline (collar/bolus/ear-tag/leg-band/
smart-scale/camera). When P2-3 lands, the corresponding row is upgraded
to a real provider with the same `id` — frontend doesn't need to know.
"""
from __future__ import annotations

from typing import Any

from packages.contracts.integrations_health_v1 import IntegrationHealth


_IOT_CLASSES: list[tuple[str, str]] = [
    ('iot.collar', 'IoT: ошейники'),
    ('iot.bolus', 'IoT: болюсы'),
    ('iot.ear_tag', 'IoT: бирки'),
    ('iot.leg_band', 'IoT: ножные браслеты'),
    ('iot.smart_scale', 'IoT: умные весы'),
    ('iot.camera', 'IoT: камеры'),
]

_NOTE_IOT = 'Запланировано в P2-3. Сейчас нет ingest pipeline.'
_NOTE_SENSOR = 'Endpoint описан (docs/integrations/sensor_ingestion_api.md); приём данных активируется в P2-3.'


class IoTStubsHealthProvider:
    def get_health(self, conn: Any) -> list[IntegrationHealth]:
        return [
            IntegrationHealth(
                id=device_id,
                name=device_name,
                kind='iot_device',
                status='disabled',
                note=_NOTE_IOT,
            )
            for device_id, device_name in _IOT_CLASSES
        ]


class SensorIngestionStubProvider:
    def get_health(self, conn: Any) -> list[IntegrationHealth]:
        return [
            IntegrationHealth(
                id='sensor.ingestion_api',
                name='Sensor Ingestion API',
                kind='sensor_ingestion',
                status='disabled',
                note=_NOTE_SENSOR,
            )
        ]


__all__ = ['IoTStubsHealthProvider', 'SensorIngestionStubProvider']
