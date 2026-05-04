# Задача PMV-B01: KPI Bridge — соединить kpi_v2 с UI

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`
- Worktree: `wt-bridge` (ветка `b/bridge`)
- Уже есть `src/genomeai/kpi_v2.py` (435 LoC, 25 KPI), функция `run_kpi(...)` возвращает `kpi_long.csv`, `kpi_wide.csv`, `kpi_alerts.csv`, `kpi_summary.json`
- Параллельно есть `web_cabinet/analytics_v1.py` (285 LoC) — пишет свой SQL прямо к таблицам, дублирует логику kpi_v2

## Цель
Создать `web_cabinet/analytics/kpi_bridge.py` — facade слой, чтобы UI вызывал legacy backend без знания о его внутренностях.

## Зоны параллельной работы (ВАЖНО!)

Этот worktree (`wt-bridge`) трогает ТОЛЬКО:
- `web_cabinet/analytics/__init__.py`
- `web_cabinet/analytics/kpi_bridge.py`
- `web_cabinet/analytics/tests/__init__.py`
- `web_cabinet/analytics/tests/test_kpi_bridge.py`

**НЕ ТРОГАЙ** (другие worktrees работают над этим):
- `web_cabinet/iot/` (wt-iot)
- `web_cabinet/analytics/statistical_extension.py` (wt-stat)
- `web_app/components/timeline/` (wt-stat)

Если нужно — создай заглушки/stubs, мерджить будем позже.

## Структура

```
web_cabinet/analytics/
├── __init__.py                  ← создать (пустой docstring)
├── kpi_bridge.py                ← главный файл
└── tests/
    ├── __init__.py
    └── test_kpi_bridge.py
```

## Главная функция

```python
@dataclass
class DashboardKPI:
    farm_id: str
    as_of: date
    # Production
    avg_milk_yield_kg: Optional[float]
    ecm_kg: Optional[float]
    fat_pct: Optional[float]
    protein_pct: Optional[float]
    scc_bulk_k: Optional[float]
    # Reproduction
    pregnancy_rate_21d_pct: Optional[float]
    days_open_avg: Optional[float]
    # Health
    cows_in_treatment: Optional[int]
    mastitis_incidence_pct_per_year: Optional[float]
    # Meta
    confidence: Literal["high", "medium", "low"]
    sample_size_cows: int
    raw_kpi_long: Optional[pd.DataFrame] = None  # для drill-down


def compute_dashboard_kpi(
    farm_id: str,
    as_of: date,
    *,
    period_days: int = 7,
) -> DashboardKPI:
    """
    Вычисляет KPI snapshot для UI Dashboard.
    Использует genomeai.kpi_v2.run_kpi() как computation engine.
    """
```

Внутри:
1. Подготовить input (data dir для kpi_v2 — для начала используй `data/fixtures/target_v2`)
2. Вызвать `kpi_v2.run_kpi(...)`
3. Прочитать `kpi_long.csv` из result
4. Извлечь нужные KPI через helper `_get_kpi(df, kpi_id)`
5. Вернуть заполненный DashboardKPI

## Acceptance criteria

1. `web_cabinet/analytics/kpi_bridge.py` создан, < 250 LoC
2. `compute_dashboard_kpi('demo-farm-v1', date.today())` возвращает заполненный DashboardKPI
3. Tests:
   - `test_compute_dashboard_kpi_synthetic` — happy path на data/fixtures/target_v2
   - `test_compute_dashboard_kpi_empty_input` — пустой input → low confidence
   - `test_dashboard_kpi_dataclass_fields_present` — все поля заполнены или None
   - `test_get_kpi_helper` — helper functions
   - `test_confidence_levels` — high/medium/low
4. `npm run typecheck` (если что-то меняли в frontend) pass — но в этой задаче frontend не трогаем
5. `pytest web_cabinet/analytics/tests/test_kpi_bridge.py` зелёный
6. Все 7 CI gates pass (если применимо в этой среде)

## Что НЕ делать

- ❌ Не переписывать `kpi_v2.py` — это legacy proven код
- ❌ Не создавать дублирующие KPI calculators
- ❌ Не трогать `analytics_v1.py` напрямую — постепенно депрекейтим в Неделе 4
- ❌ Не трогать `web_cabinet/__init__.py` (там регистрация роутеров, могут конфликтовать с другими worktrees)

## Endpoint update — НЕ в этой задаче

Endpoint `/api/dashboard/today` будет переключен на bridge **в следующей итерации** (День 5). Сейчас просто создай bridge + tests.

## Формат ответа

Scope → План → Deliverables → Acceptance → Проверки → Риски → От координатора.  
Статус: `proven` / `partially_proven` / `not_proven` / `blocked`.  
Файл: `docs/iterations/PMV-B01_execution_proof.md`.
