"""POST /api/sensors/ingest — stub (501 Not Implemented), full impl in PMV-B05 Week 5."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class SensorReading(BaseModel):
    animal_id: str
    timestamp: datetime
    metrics: dict[str, float]


class SensorIngestPayload(BaseModel):
    tenant_id: str
    gateway_id: str
    gateway_token: str
    vendor: str
    readings: list[SensorReading]


@router.post("/ingest", status_code=501)
async def ingest_sensor_data(payload: SensorIngestPayload) -> JSONResponse:
    """
    Принимает пакет sensor readings от IoT-шлюза.

    Stub: возвращает 501 до полной реализации в PMV-B05 (Week 5).
    Полная реализация будет включать:
      1. HMAC-верификацию gateway_token
      2. Нормализацию через vendor adapter (Heatime / Nedap / Allflex / generic)
      3. QC-валидацию через genomeai.qc_v2.run_qc_v2()
      4. Агрегацию в daily metrics
      5. UPSERT в dm_sensors_daily
      6. Async trigger anomaly detection
    """
    return JSONResponse(
        status_code=501,
        content={
            "status": "not_implemented",
            "message": "POST /api/sensors/ingest is a placeholder — full implementation in PMV-B05 Week 5.",
            "received": {
                "tenant_id": payload.tenant_id,
                "gateway_id": payload.gateway_id,
                "vendor": payload.vendor,
                "reading_count": len(payload.readings),
            },
        },
    )
