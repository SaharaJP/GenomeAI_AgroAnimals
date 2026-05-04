# Задача PMV-B02-sensor: Sensor Bridge

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`
- Worktree: `wt-iot` (ветка `b/iot`)
- В архиве есть `src/genomeai/sensor_anomaly_v1.py` (388 LoC, smoke-проверено)
- 3 типа аномалий: `data_dropout`, `outlier`, `baseline_drift`
- API: `detect_sensor_anomalies(df, cfg=DetectorConfig())` — параметр `cfg`, не `config`

## Цель
Создать `web_cabinet/analytics/sensor_bridge.py` — wrapper над `sensor_anomaly_v1`. UI будет вызывать его для отображения текущих sensor аномалий.

## Зоны параллельной работы

Этот worktree (`wt-iot`) трогает ТОЛЬКО:
- `web_cabinet/analytics/sensor_bridge.py`
- `web_cabinet/analytics/tests/test_sensor_bridge.py`

**НО ВНИМАНИЕ:** этот файл лежит в `web_cabinet/analytics/`, где также работают другие worktrees. Чтобы избежать конфликтов:
1. Создавай **только** свой файл `sensor_bridge.py`
2. НЕ трогай `kpi_bridge.py` или `statistical_extension.py`
3. НЕ трогай `web_cabinet/analytics/__init__.py` без необходимости (если уже есть)

## Что реализовать

```python
@dataclass
class SensorAnomalyAlert:
    animal_id: str
    metric: str          # "activity_count", "rumination_min", "body_temp_c"
    anomaly_type: Literal["data_dropout", "outlier", "baseline_drift"]
    detected_at: date
    severity: Literal["critical", "warning", "info"]
    raw_data: dict


def detect_recent_sensor_anomalies(
    farm_id: str,
    lookback_days: int = 30,
    cfg: Optional[DetectorConfig] = None,
) -> list[SensorAnomalyAlert]:
    """Получить sensor data из БД (или CSV для dev),
    запустить detect_sensor_anomalies, вернуть Alerts."""
```

Внутри:
1. Загрузить sensor data:
   - Если `GENOMEAI_DB_DSN` задан → SQL запрос к `dm_sensors_daily`
   - Иначе → CSV `data/demo/demo_farm_v1/dm_sensors_daily.csv`
2. Вызвать `detect_sensor_anomalies(df, cfg=cfg)` (помни `cfg=`!)
3. Конвертировать pd.DataFrame в list[SensorAnomalyAlert]
4. Severity computation:
   - `data_dropout` → critical
   - `outlier` с z>5 → critical, иначе warning
   - `baseline_drift` → warning

## Acceptance criteria

1. `detect_recent_sensor_anomalies('demo-farm-v1')` работает на demo CSV
2. Tests:
   - `test_sensor_bridge_synthetic` — на dm_sensors_daily.csv (мало данных, ожидается 0 anomalies)
   - `test_severity_computation` — все 3 типа anomaly
   - `test_empty_input_returns_empty_list`
   - `test_invalid_farm_id_returns_empty_list`

## Формат ответа

T34 — `docs/iterations/PMV-B02-sensor_execution_proof.md`.
