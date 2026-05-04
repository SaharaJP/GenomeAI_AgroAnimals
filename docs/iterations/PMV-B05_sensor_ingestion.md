# Задача PMV-B05: Real-time Sensor Ingestion REST

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`
- Worktree: `wt-iot` (ветка `b/iot`)
- Skeleton уже создан в Дне 6 (web_cabinet/iot/__init__.py + 501 endpoint stub)
- Sensor data сейчас приходит только batch CSV
- Для современных IoT датчиков (collar Heatime, Nedap, Allflex) нужен REST endpoint

## Цель
Полная имплементация `POST /api/sensors/ingest` — принимает JSON с массивом sensor readings, валидирует через QC, агрегирует в daily, сохраняет в `dm_sensors_daily`.

Это **stub** — без MQTT, без real-time alerts. Просто accept + persist.

## Зоны параллельной работы

Этот worktree трогает ТОЛЬКО:
- `web_cabinet/iot/__init__.py`
- `web_cabinet/iot/endpoints.py`
- `web_cabinet/iot/vendors/__init__.py`
- `web_cabinet/iot/vendors/heatime.py`
- `web_cabinet/iot/vendors/generic.py`
- `web_cabinet/iot/tests/test_ingest.py`
- `docs/integrations/sensor_ingestion_api.md`

НЕ ТРОГАЙ:
- `web_cabinet/analytics/` (wt-bridge, wt-stat)
- `web_app/`

## Endpoint

```python
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

@router.post("/api/sensors/ingest")
async def ingest_sensor_data(payload: SensorIngestPayload):
    """
    1. Auth (HMAC token verification — stub для начала)
    2. Vendor adapter normalization
    3. QC validation через genomeai.qc_v2.run_qc_v2()
    4. Aggregate to daily
    5. UPSERT в dm_sensors_daily
    6. Trigger anomaly detection (async, non-blocking)
    """
```

## Vendor adapters

```python
# vendors/heatime.py
def transform_heatime_payload(raw: dict) -> list[SensorReading]:
    """Convert SCR Heatime format to canonical."""
    # Heatime отдаёт: {device_id, animal_tag, observations: [{ts, activity_idx, rumination_minutes}]}
    pass

# vendors/generic.py
def transform_generic_payload(raw: dict) -> list[SensorReading]:
    """Pass-through для уже canonical формата."""
    pass
```

## Aggregation logic

```python
def _aggregate_to_daily(readings: list[SensorReading]) -> pd.DataFrame:
    """
    Группируем по (animal_id, date) → daily aggregates:
    - activity_count = sum
    - rumination_min = sum
    - lying_min = sum
    - body_temp_c = avg (или max?)
    """
```

## Acceptance criteria

1. POST с valid JSON → 200 + ingested_count
2. POST без token → 401
3. POST с invalid metrics (вне range) → QC warnings в response (не отвергает если warning)
4. POST с future timestamp → BLOCKER → отвергает
5. Idempotency — повторный POST same payload не дублирует rows (UPSERT, не INSERT)
6. Tests (минимум 6):
   - `test_ingest_valid_payload`
   - `test_auth_failure_401`
   - `test_qc_warning_does_not_reject`
   - `test_qc_blocker_rejects`
   - `test_idempotency`
   - `test_heatime_vendor_transform`

## Документация

`docs/integrations/sensor_ingestion_api.md`:
- Endpoint URL, auth scheme (HMAC + tenant_id)
- Request/Response schema
- Curl examples (3 разных vendor)
- QC rules table (что отвергается с status, что warning)
- Rate limits (1000 readings per request, 100 requests/minute per gateway)
- Error codes (401, 422, 429, 500)

## Формат ответа

T34 — `docs/iterations/PMV-B05_execution_proof.md` + curl examples проверенные руками.
