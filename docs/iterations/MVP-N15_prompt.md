# Задача MVP-N15: Insight Scanner (background AI agent)

**PROMPT:**

## Контекст
- AI-gateway: MVP-N11
- Farm context + tools: MVP-N12
- Insights UI: MVP-N03

## Цель
Background AI-агент, который каждые 6 часов сканирует данные фермы и **сам** создаёт новые insights. Это делает AI проактивным.

## Backend

### web_cabinet/ai/background/insight_scanner.py

```python
def scan_for_new_insights(farm_id: str) -> list[Insight]:
    """
    Сканирует данные фермы за последние 12 часов,
    находит аномалии и создаёт новые insights.
    """
    # 1. Load full context с deep details
    context = build_farm_context(farm_id, period_days=1, include_cow_details=True)
    
    # 2. Load existing active insights (чтобы не дублировать)
    existing = get_active_insights(farm_id)
    
    # 3. Call Claude Sonnet с tools (может копаться в деталях)
    response = client.tool_call(
        system=INSIGHT_SCANNER_SYSTEM,
        user=f"Найди новые insights. Контекст: {context}. Существующие: {existing}",
        tools=ALL_FARM_TOOLS,
        max_tokens=3000,
    )
    
    # 4. Parse JSON response с массивом Insight
    new_insights = parse_insights(response)
    
    # 5. Validate evidence для каждого
    valid_insights = [i for i in new_insights if validate_evidence(i)]
    
    # 6. Save в БД со status="to_check"
    for insight in valid_insights:
        save_insight(insight)
    
    return valid_insights
```

### Pydantic модель Insight
```python
class Insight(BaseModel):
    insight_id: str
    farm_id: str
    title: str  # "Падение удоя в группе 3 на 8% за 3 дня"
    description: str  # с evidence
    category: Literal["production", "reproduction", "health", "feeding", "welfare", "economics"]
    priority: Literal["high", "medium", "low"]
    status: Literal["to_check", "to_follow_up", "done"] = "to_check"
    affected_cow_ids: list[str]
    affected_group_ids: list[str]
    evidence_ids: list[str]
    recommendations: list[Recommendation]
    generated_at_utc: datetime
    generator: str  # "ai_scanner" | "rule_based" | "manual"

class Recommendation(BaseModel):
    action: str
    priority: Literal["high", "medium", "low"]
    role: Literal["vet", "zootech", "operator", "director"]
    due_hint: str | None  # "в течение 24 часов"
```

### INSIGHT_SCANNER_SYSTEM prompt
(полный prompt, русский, жёсткие правила)

Приоритеты при выборе insights:
- HIGH: food-safety issues, клинические эпизоды, production drop > 10%
- MEDIUM: trend shifts > 5%, reproduction issues, BCS drift
- LOW: optimization opportunities, preventive observations

Категории (max 1 insight per category):
- production / reproduction / health / feeding / welfare / economics

Требования:
- 3-5 insights за вызов (не больше)
- Каждый с evidence_ids
- Recommendations concrete (не generic)
- Не дублировать existing active insights

## Cron

APScheduler:
```python
scheduler.add_job(
    run_insight_scanner_for_all_farms,
    'cron',
    hour='*/6',  # каждые 6 часов
    minute=15
)
```

В .env.ai: `GENOMEAI_AI_INSIGHT_SCANNER_CRON=0 */6 * * *`

## Уведомление frontend

После создания insights — через Redis pub/sub публикуется событие. SSE endpoint `/api/insights/events/stream` пушит на открытые UI. На Обзоре появляется notification bubble: "3 новых инсайта".

## Demo mode

В demo-режиме — seeded insights в БД. Scanner не запускается на реальных данных.

Но для демо можно добавить "manual trigger" кнопку:
- `POST /api/insights/scan-now` (admin only)
- При клике в UI → "Сканирую... Готово! 2 новых инсайта"
- Возвращает already-seeded "fake new" insights из отдельного JSON

## Deliverables
- `web_cabinet/ai/background/insight_scanner.py`
- `web_cabinet/ai/prompts/insight_scanner.py`
- `web_cabinet/api/insights/scan_now.py` (manual trigger endpoint)
- `web_cabinet/api/insights/events_stream.py` (SSE для notifications)
- `web_app/components/ai/insight-notification-bell.tsx` (в topbar)
- APScheduler registration
- Tests: test_insight_scanner.py (mock Claude, check parse + validate)
- `docs/iterations/MVP-N15_execution_proof.md`

## Acceptance criteria
1. Cron запускается (тест через short interval)
2. Scanner генерит valid Insights с evidence
3. No duplicates с existing active insights
4. Manual trigger endpoint работает
5. SSE notification appears в UI
6. Все CI гейты pass

## Формат ответа
Стандартный T34.
