# Задача PMV-B02-alerts: Alerts Bridge

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`
- Worktree: `wt-bridge` (ветка `b/bridge`)
- PMV-B01 уже завершён (kpi_bridge готов)
- В архиве есть `src/genomeai/alerts_v2.py` (755 LoC, 11 alert generators)

## Цель
Создать `web_cabinet/analytics/alerts_bridge.py` — wrapper над `alerts_v2`, чтобы Connecterra `/api/insights` brake real alerts из БД.

## Зоны параллельной работы

Этот worktree трогает ТОЛЬКО:
- `web_cabinet/analytics/alerts_bridge.py`
- `web_cabinet/analytics/tests/test_alerts_bridge.py`

НЕ ТРОГАЙ:
- `web_cabinet/iot/` (wt-iot)
- `web_cabinet/analytics/statistical_extension.py` (wt-stat)
- `web_app/` (wt-stat / wt-iot)

## Что нужно реализовать

```python
@dataclass
class ActiveAlert:
    alert_id: str
    farm_id: str
    animal_id: Optional[str]
    alert_type: str  # см. alerts_v2 catalog
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    detected_at: date
    evidence: dict  # references к event_ids, kpi values
    

def list_active_alerts(
    farm_id: str,
    *,
    severity_filter: Optional[list[str]] = None,
    limit: int = 50,
) -> list[ActiveAlert]:
    """Wrapper над genomeai.alerts_v2.run_alerts() / list_active.
    
    Возвращает только активные (не разрешённые) alerts из БД.
    """
```

Внутри:
1. Изучи `alerts_v2.py` — какая функция выдаёт active alerts
2. Если есть `run_alerts(...)` который пишет в БД — вызывай и читай
3. Если только in-memory list — выбери самый подходящий API
4. Адаптируй output под UI structure (severity normalization, sort by severity DESC + detected_at DESC)

## Acceptance criteria

1. `alerts_bridge.list_active_alerts('demo-farm-v1')` возвращает list[ActiveAlert]
2. Если alerts_v2 не выдаёт ничего на synthetic data — попробуй на 350 коров investor_v1 (ожидается 5-15 alerts)
3. Tests:
   - `test_list_active_alerts_returns_list`
   - `test_severity_normalization` — alerts_v2 может использовать другие labels (high/medium/low) → нормализуй
   - `test_filter_by_severity`
   - `test_limit_param`

## Формат ответа

T34 — `docs/iterations/PMV-B02-alerts_execution_proof.md`.
