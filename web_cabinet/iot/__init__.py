"""IoT sensor ingestion — skeleton for PMV-B05 (Week 5 full implementation)."""
from __future__ import annotations

from fastapi import FastAPI


def register_iot_routes(app: FastAPI) -> None:
    from .endpoints import router as iot_router

    app.include_router(iot_router, prefix="/api/sensors", tags=["iot-sensors"])
