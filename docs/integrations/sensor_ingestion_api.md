# Sensor Ingestion API — черновик (PMV-B05)

> **Статус**: Skeleton / 501 stub. Полная реализация — PMV-B05 Week 5.

## Endpoint

```
POST /api/sensors/ingest
Content-Type: application/json
```

## Headers

| Header | Обязательный | Описание |
|--------|-------------|---------|
| `Content-Type` | да | `application/json` |
| `X-Gateway-Token` | планируется | HMAC-токен шлюза (Week 5) |

## Body Schema

```json
{
  "tenant_id": "farm_001",
  "gateway_id": "gw-collar-01",
  "gateway_token": "hmac-sha256-stub",
  "vendor": "heatime",
  "readings": [
    {
      "animal_id": "A1234",
      "timestamp": "2026-05-04T06:00:00Z",
      "metrics": {
        "activity": 85.3,
        "rumination_min": 420.0,
        "temp_vaginal": 38.7
      }
    }
  ]
}
```

### Поля

| Поле | Тип | Описание |
|------|-----|---------|
| `tenant_id` | string | ID фермы / тенанта |
| `gateway_id` | string | Уникальный ID шлюза |
| `gateway_token` | string | Токен аутентификации шлюза |
| `vendor` | string | `heatime` / `nedap` / `allflex` / `generic` |
| `readings[].animal_id` | string | ID животного в системе |
| `readings[].timestamp` | ISO 8601 datetime | Время измерения (UTC) |
| `readings[].metrics` | object | Словарь метрик (float values) |

### Поддерживаемые vendor

| Vendor | Метрики |
|--------|---------|
| `heatime` | `activity`, `rumination_min` |
| `nedap` | `activity`, `feeding_time_min`, `milk_yield_l` |
| `allflex` | `activity`, `temp_vaginal`, `rumination_min` |
| `generic` | любые float-метрики |

## Curl examples

### Stub (текущее поведение — 501)

```bash
curl -X POST http://localhost:8000/api/sensors/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "farm_001",
    "gateway_id": "gw-collar-01",
    "gateway_token": "test-token",
    "vendor": "heatime",
    "readings": [
      {
        "animal_id": "A1234",
        "timestamp": "2026-05-04T06:00:00Z",
        "metrics": {"activity": 85.3, "rumination_min": 420.0}
      }
    ]
  }'
```

**Ответ (501)**:
```json
{
  "status": "not_implemented",
  "message": "POST /api/sensors/ingest is a placeholder — full implementation in PMV-B05 Week 5.",
  "received": {
    "tenant_id": "farm_001",
    "gateway_id": "gw-collar-01",
    "vendor": "heatime",
    "reading_count": 1
  }
}
```

## Что будет в PMV-B05 Week 5

1. **HMAC-верификация** `gateway_token` (секрет шлюза из Postgres `gateway_secrets`)
2. **Vendor adapter normalization** — `web_cabinet/iot/vendors/heatime.py`, `nedap.py`, `allflex.py`, `generic.py`
3. **QC-валидация** через `genomeai.qc_v2.run_qc_v2()` — отбраковка выбросов
4. **Агрегация в daily** — группировка readings по `animal_id` + дата
5. **UPSERT в `dm_sensors_daily`** — через Alembic-миграцию, схема: `(tenant_id, animal_id, date, vendor, metrics jsonb)`
6. **Async anomaly trigger** — вызов `sensor_anomaly_v1` (sensor_bridge) без блокировки
7. **Ответ 202 Accepted** с `ingest_id` для отслеживания

## Структура кода (skeleton)

```
web_cabinet/iot/
├── __init__.py          # register_iot_routes(app)
├── endpoints.py         # POST /ingest stub (501)
└── vendors/
    └── __init__.py      # vendor adapters (Week 5)
```
