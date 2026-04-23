# Задача MVP-N12: Farm context builder + Tool definitions

**PROMPT:**

## Контекст
- MVP-N11 создал skeleton `web_cabinet/ai/context.py` и `web_cabinet/ai/tools.py`
- Теперь — полная реализация

## Цель
Сделать ИИ-помощника действительно "умным" — реально видящим данные фермы и умеющим докапываться до деталей через tool use.

## 1. build_farm_context()

```python
def build_farm_context(
    farm_id: str,
    *,
    include_cow_details: bool = False,
    specific_cow_ids: list[str] | None = None,
    period_days: int = 7,
) -> dict:
    """
    Формирует snapshot фермы для передачи в Claude.
    ~2000-5000 токенов. Измеряется через tiktoken.
    """
```

Включает:

### farm_summary
- name, total_cows, active_cows_count, date_as_of

### today_kpi
- milk_yield_avg_kg_per_cow
- scc_bulk_k
- fresh_cows_count
- cows_in_withdrawal_count
- conception_rate_21d_pct
- health_index_score (0-100)

### period_trends (vs previous period_days)
- Каждый KPI + delta + direction (↑/↓/→)

### active_insights (status in to_check, to_follow_up)
Краткие описания с priority

### recent_events (last 50 за period_days)
Compact формат: {date, type, title, cow_id|group_id, evidence_id}

### attention_cows
Коровы с флагами:
- falling_yield (drop > 10% за 7 дней)
- active_treatment (в процессе лечения)
- missed_heat (прошли без heat detection)
- high_scc (> 200k)
- post_mastitis (в восстановлении)
- ready_for_culling (NPV < 0)
- overdue_preg_check

### groups_summary
По каждой группе: cow_count, avg_yield, health_status_summary

### Если specific_cow_ids — добавить full_profile для них
- Full history по этим коровам (overlap с tool get_cow_history)

## 2. Tool definitions (tools.py)

7 tools для Claude tool use:

### 2.1 get_cow_history(cow_id, days_back=30)
Полная история коровы: events, treatments, daily milk yields, BCS, group moves, reproduction.

### 2.2 get_group_metrics(group_id, period="7d")
DMI, ECM, SCC, health events count, reproduction stats за период.

### 2.3 search_events(event_types, cow_ids, date_from, date_to, limit=50)
Поиск событий по фильтрам.

### 2.4 get_treatment_records(status="all", cow_ids=None)
Лечения и withdrawal статусы. status in ["active", "completed", "all"].

### 2.5 get_reproduction_status(cow_ids=None, group_id=None)
Воспроизводство: last_heat, last_breeding, preg_check_status, DIM, VWP.

### 2.6 get_milk_quality_trend(cow_id, group_id, period="30d")
SCC, conductivity, fat, protein trends.

### 2.7 get_economics_snapshot(cow_id=None)
NPV, daily cash flow, break-even projection.

### Каждый tool
- Pydantic input schema
- Anthropic tool definition format:
  ```python
  {
      "name": "get_cow_history",
      "description": "Получить полную историю коровы: события за N дней, лечения, удой по дням, BCS, переводы групп. Используй когда нужны детали конкретной коровы.",
      "input_schema": {...}
  }
  ```
- Implementation: query Postgres через existing web_cabinet db session
- Response: JSON-serializable dict
- Max output size: 5000 tokens (truncate older data если больше)

## 3. Интеграция

### В prompts где используются tools
Расширить ASK_FARM_SYSTEM:
```
У тебя есть доступ к следующим функциям для получения дополнительных данных:
- get_cow_history: детальная история коровы
- get_group_metrics: метрики группы за период
- search_events: поиск событий
- get_treatment_records: лечения и withdrawals
- get_reproduction_status: статус воспроизводства
- get_milk_quality_trend: тренды качества молока
- get_economics_snapshot: экономика

Используй их когда farm_context недостаточно для точного ответа.
Не вызывай tools без необходимости — это дорого и медленно.
```

### Evidence IDs
Каждое событие в контексте и в tool responses имеет `evidence_id` (== event_id в БД).
AI подкрепляет claims ссылками: `[evidence: event_12482]`.

### Post-processing
В endpoint ask-farm: после получения ответа AI → extract evidence ids → validate они существуют в БД → если нет, пометить ответ флагом "unverified_evidence".

## Tests

### test_context.py
- test_farm_context_structure — все обязательные поля есть
- test_farm_context_token_count — не превышает 10000 токенов на fresh demo data
- test_attention_cows_detection — правильно флагует Звёздочку (falling_yield), Малину (ready_for_culling), Ночку (high_scc)
- test_period_trends — delta корректно считается

### test_tools.py
- test_get_cow_history_4821 — возвращает все 60-дневные events Звёздочки включая mastitis episode
- test_search_events_by_type — фильтр работает
- test_get_treatment_records_active — возвращает 5 seeded withdrawals
- test_get_reproduction_status_group — корректная агрегация по группе
- Все tools на seeded data из `data/demo/investor_v1/`

## Deliverables
- `web_cabinet/ai/context.py` — full implementation
- `web_cabinet/ai/tools.py` — all 7 tools
- `web_cabinet/ai/context_helpers/` — вспомогательные queries
- `tests/web_cabinet/ai/test_context.py`
- `tests/web_cabinet/ai/test_tools.py`
- `docs/iterations/MVP-N12_execution_proof.md`

## Acceptance criteria
1. build_farm_context("demo-farm-v1") возвращает valid dict < 10000 токенов
2. Все 7 tools с implementation + tests + Anthropic tool definition
3. tiktoken подсчёт подтверждает ~2000-5000 токенов для typical context
4. Все tests pass
5. Все 7 CI гейтов pass

## Формат ответа
Стандартный T34.
