# MVP-N04-data: Aggregated metrics для Analytics tabs — Execution Proof

## Scope

Реализация трёх REST endpoints агрегированных метрик для Analytics страницы (MVP-N04).
Эндпоинты читают данные из demo farm v1 (seeded), возвращают JSON time series.

---

## Deliverables

| Артефакт | Статус |
|---|---|
| `packages/contracts/analytics_v1.py` | создан |
| `web_cabinet/analytics_v1.py` | создан |
| `src/web_cabinet/analytics_v1.py` | создан (mirror для pytest path) |
| `web_cabinet/app.py` + `src/web_cabinet/app.py` | обновлены (include_router) |
| `src/core/infra/web_db.py` | обновлён (`_ensure_target_dm_schema` в `init_db`) |
| `tests/web/test_analytics_endpoints.py` | создан, 25 тестов |
| `docs/public_interfaces.json` | обновлён (секция `analytics_api`) |

---

## Executed checks

### Тест-сьют (runtime proven)

```
pytest tests/web/test_analytics_endpoints.py -v
======================= 25 passed in 20.51s =======================
```

**Полный список (25/25 PASS):**
- `test_production_returns_200`
- `test_production_schema_field`
- `test_production_time_series_has_3_dates`
- `test_production_aggregation_9_animals_per_day`
- `test_production_avg_milk_within_range`
- `test_production_ecm_computed`
- `test_production_summary_total_records`
- `test_production_farm_filter`
- `test_production_empty_range`
- `test_production_requires_auth`
- `test_reproduction_returns_200`
- `test_reproduction_schema_field`
- `test_reproduction_events_total`
- `test_reproduction_inseminations_count`
- `test_reproduction_days_open_populated`
- `test_reproduction_vwp_default`
- `test_reproduction_requires_auth`
- `test_health_returns_200`
- `test_health_schema_field`
- `test_health_events_total`
- `test_health_mastitis_count`
- `test_health_breakdown_all_types_present`
- `test_health_breakdown_pct_sums_to_100`
- `test_health_empty_range`
- `test_health_requires_auth`

### Endpoints и их контракты

**GET /api/analytics/production**
```json
{
  "schema": "genomeai.api.analytics.production.v1",
  "start_date": "2025-03-01",
  "end_date": "2025-04-30",
  "time_series": [
    {"date": "2025-03-22", "avg_milk_kg": 31.27, "ecm_kg": 32.61, "avg_fat_pct": 3.9, "avg_protein_pct": 3.19, "avg_scc_cells_ml": 222000, "n_records": 9},
    {"date": "2025-03-29", "avg_milk_kg": 31.67, "ecm_kg": 33.03, ...},
    {"date": "2025-04-05", "avg_milk_kg": 32.07, "ecm_kg": 33.45, ...}
  ],
  "summary": {"avg_milk_kg": 31.67, "avg_ecm_kg": 33.03, "total_records": 27}
}
```

**GET /api/analytics/reproduction**
```json
{
  "schema": "genomeai.api.analytics.reproduction.v1",
  "conception_rate": null,
  "days_open_by_lactation": [{"lactation_no": 2, "avg_days_open": 59.0, "n_animals": 1}],
  "vwp_days": 50, "inseminations": 1, "events_total": 5
}
```

**GET /api/analytics/health**
```json
{
  "schema": "genomeai.api.analytics.health.v1",
  "mastitis_count": 1,
  "health_issues_breakdown": [
    {"event_type": "ketosis_risk", "count": 1, "pct": 25.0},
    {"event_type": "lameness", "count": 1, "pct": 25.0},
    {"event_type": "mastitis", "count": 1, "pct": 25.0},
    {"event_type": "metritis", "count": 1, "pct": 25.0}
  ],
  "events_total": 4
}
```

---

## Net result

- Все 3 endpoint возвращают валидный JSON с правильными schema-strings
- Demo farm data (27 milkings × 9 cows, 5 repro, 4 health events) корректно агрегируется
- Фильтры `start_date`, `end_date`, `farm_id` работают (verified by tests)
- Auth guard работает: без логина → 401/403
- ECM вычисляется по формуле Sjaunja 1990
- days_open: DEMO_COW_2001 (calving 2025-01-20, insemination 2025-03-20) → 59 дней ✓
- Pydantic models работают без ошибок, только expected UserWarning на field name "schema"

---

## Технические решения

- **`_ensure_target_dm_schema`** добавлен в `init_db` для создания `dm_farms`, `dm_animals`,
  `dm_lactations`, `dm_milkings_daily`, `dm_health_events`, `dm_repro_events` через SQLite
  (без FK constraints, идемпотентный `IF NOT EXISTS`)
- **src/web_cabinet/** — pytest-видимый путь: `src/` стоит первым в `sys.path` (conftest.py),
  поэтому `analytics_v1.py` продублирован туда и там же обновлён `app.py`
- **Permission**: `kpi.view` — присутствует у Viewer, Zootech, Vet, Operator, Director, Admin
- **try/except** вокруг каждого SQL-запроса: если таблица отсутствует (Postgres без миграции),
  endpoint возвращает пустой результат, не 500

---

## Риски/допущения

- ECM вычислен из усреднённых fat_pct/protein_pct (не per-animal) — допустимая аппроксимация для MVP
- `pregnancy_rate` всегда `null` — для корректного вычисления нужен объём eligible animals
  (не доступен из demo data без cow_status integration)
- `src/web_cabinet/analytics_v1.py` — дублирование файла; при рефакторинге нужно будет устранить
  (задача: настроить conftest.py на использование `web_cabinet/` напрямую)

---

## Honest status

**`partially_proven`**

- **proven**: 25/25 pytest tests pass на SQLite + seeded demo data
- **not_proven**: прогон на Postgres (T34 adult контур) не выполнен
- **not_proven**: полные 7 CI gates не прогнаны (scope задачи — MVP-N04-data, не T34 гейты)
