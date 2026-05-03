# Задача MVP-N16: Impact Narrative Generator

**PROMPT:**

## Контекст
- AI-gateway: MVP-N11
- Farm context: MVP-N12
- Farm Timeline UI: MVP-N05

## Цель
AI описывает влияние каждого события на ферме словами — превращает "холодные цифры" (before/after) в осмысленный narrative с интерпретацией и рекомендациями.

## Backend

### POST /api/ai/impact-narrative

Request:
```json
{
  "event_id": "event_12482",
  "window": "3d" | "1w" | "2w" | "4w",
  "language": "ru"
}
```

Response (Pydantic ImpactNarrative):
```python
class ImpactNarrative(BaseModel):
    event_id: str
    window: str
    narrative: str  # 2-3 предложения с оценкой влияния
    interpretation: Literal["positive", "negative", "neutral", "mixed"]
    significance: Literal["major", "moderate", "minor", "insignificant"]
    recommendations: list[str]  # 1-3 actionable items
    confidence: float  # 0.0 - 1.0 (уверенность LLM в интерпретации)
    generation_model: str
```

### Логика
1. Load event details из БД
2. Рассчитать before/after metrics за window
3. Call Claude Sonnet 4.6 с IMPACT_NARRATIVE_SYSTEM prompt
4. Контекст содержит:
   - event: {type, date, description, affected_groups}
   - before_metrics: {metric_name: {value, period}}
   - after_metrics: {metric_name: {value, period}}
   - related_events: другие events в окне (чтобы AI учёл confounders)
5. Parse response → ImpactNarrative
6. Cache 24h (одинаковое событие в одинаковом окне = одинаковый narrative)

### IMPACT_NARRATIVE_SYSTEM prompt
(полный, русский)

Ключевые требования:
- 2-3 предложения narrative
- Первое: констатация факта с числами
- Второе: интерпретация значимости (норма / проблема / улучшение)
- Третье: короткий вывод или рекомендация

Пример хорошего narrative:
"Смена рациона 11 марта привела к падению DMI на 1.1 кг/голову (−5.6%) в группах 1, 12 и 2. Одновременно ECM вырос на 0.1 кг — значит эффективность корма повысилась. Рекомендуется наблюдать следующие 2 недели за удоем, а также проверить корреляцию с ростом THI (+2)."

Запрещено:
- Выдумывать причинно-следственные связи без evidence в related_events
- Generic фразы "рекомендуется мониторить"
- Утверждения вне предоставленных метрик

## Интеграция с frontend

### В MVP-N05 Farm Timeline → Impact Panel
- Под "Что ещё случилось?" добавляется **"Интерпретация ИИ-помощника"** section
- Показывается narrative с бирюзовой левой полосой
- Significance badge (цвет зависит от interpretation)
- Recommendations как bulleted list

### Кэш
Первый раз для события — LLM call (1-2 сек).
Повторный — из Redis (< 50ms).

## Demo mode
В demo-режиме seeded impact narratives из `data/demo/investor_v1/seeded_impact_narratives.json` для 8 главных demo events.

## Deliverables
- `web_cabinet/ai/endpoints/impact_narrative.py`
- `web_cabinet/ai/prompts/impact_narrative.py` (полный prompt)
- `web_app/components/timeline/impact-narrative-section.tsx`
- Интеграция в `web_app/components/timeline/impact-panel.tsx` (из MVP-N05)
- Tests: test_impact_narrative.py (mock Claude, проверка parse + validation)
- `docs/iterations/MVP-N16_execution_proof.md`

## Acceptance criteria
1. POST /api/ai/impact-narrative возвращает валидный ImpactNarrative
2. Narrative на русском, 2-3 предложения
3. Significance и interpretation корректно классифицируются на типовых кейсах
4. Кэширование работает (второй запрос < 100ms)
5. Интеграция в Impact Panel: narrative section отображается под metric cards
6. Все CI гейты pass

## Формат ответа
Стандартный T34.
