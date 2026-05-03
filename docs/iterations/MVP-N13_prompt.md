# Задача MVP-N13: Виджет "ИИ-помощник" на Обзоре (ask-farm)

**PROMPT:**

## Контекст
- `CLAUDE.md`, `design_decisions.md`
- Backbone: MVP-N11 (AI-gateway)
- Context + tools: MVP-N12
- Overview: MVP-N02 (страница /dashboard)

## Цель
Добавить на Обзор компактный виджет "ИИ-помощник" с preset-вопросами + интерактивный Q&A.

## UI (на странице /dashboard)

### Где размещаем
Добавляется как **4-я колонка** на dashboard справа (если достаточно ширины) или как **полноширинная карточка** под 3-колоночной сеткой.

### Дизайн карточки
- Заголовок: "🤖 ИИ-помощник" (или иконка Sparkles)
- Subtitle: "Спросите о ферме"
- Input: "Задайте вопрос о ферме..." (placeholder)
- 3 preset-chips под input:
  - "Почему упал удой у Звёздочки?"
  - "Кого рекомендуется выбраковать?"
  - "Какие коровы в охоте сегодня?"
- При submit / клик на preset → stream response inline

### Response rendering
Во время streaming:
- "ИИ-помощник думает..." с dots animation
- Текст появляется token-by-token
- Evidence chips выделяются бирюзовым

Готовый ответ:
- Чистый текст с evidence chips inline `[Звёздочка (4821)]`, `[event от 11 марта]`
- Клик по chip → открывается drawer с event details
- Ниже: кнопки "Ещё вопрос" / "Копировать" / "Поделиться"

### Mobile
На < 768px — виджет во всю ширину как bottom sheet, при клике разворачивается fullscreen modal.

## Backend endpoint

### POST /api/ai/ask-farm (SSE streaming)

Request:
```json
{
  "question": "Почему упал удой у Звёздочки?",
  "farm_id": "demo-farm-v1",
  "language": "ru",
  "session_id": "uuid" // optional, для memory
}
```

Response (SSE stream):
```
event: start
data: {"session_id": "xxx", "model": "claude-sonnet-4-6"}

event: token
data: {"text": "У Звёздочки"}

event: token
data: {"text": " (4821)"}

event: evidence
data: {"type": "cow", "id": "4821", "name": "Звёздочка"}

event: token
data: {"text": " действительно"}

... (много token events)

event: tool_call
data: {"tool": "get_cow_history", "args": {"cow_id": "4821"}}

event: tool_result
data: {"tool": "get_cow_history", "result_preview": "..."}

... (продолжение генерации)

event: done
data: {
  "total_tokens": {"input": 3200, "output": 450},
  "evidence_ids": ["event_12482", "event_12502", ...],
  "validated_evidence": true
}
```

### Backend logic
1. Проверить rate limit (user_id)
2. Если demo_mode + preset question → cached response
3. Иначе:
   a. Build farm_context с include_cow_details, specific_cow_ids extracted from question
   b. Call Claude Sonnet 4.6 с tools (из MVP-N12)
   c. Handle tool_use: execute tool, pass result back, continue
   d. Stream tokens as they arrive
   e. Post-process: extract evidence_ids, validate
   f. Save session to Redis (TTL 1 hour)
4. Log LLM call (structured JSON)

### Session memory
- Ключ: `ai:session:<session_id>` в Redis, TTL 3600s
- Хранит: list of messages (user/assistant), обрезается до 10 последних

## Demo-specific preset answers

Для 3 preset questions:
1. "Почему упал удой у Звёздочки?" — pre-computed answer (<2s response)
2. "Кого рекомендуется выбраковать?" — pre-computed
3. "Какие коровы в охоте сегодня?" — pre-computed

Хранятся в `data/demo/investor_v1/preset_ai_answers.json`.

При GENOMEAI_AI_DEMO_MODE=true — эти вопросы отдаются instantly из cache.

## Frontend implementation

### components/ai/ask-farm-widget.tsx
- Использует EventSource API для SSE
- Parsing SSE events и обновление state
- Evidence chips — отдельный React component clickable

### lib/ai-client.ts
- `askFarm(question, sessionId?)` → AsyncGenerator of events
- `parseEvidence(text)` → extracted chips

### components/ai/evidence-chip.tsx
- Clickable, opens drawer
- Shows tooltip on hover: "Открыть детали"

### components/ai/evidence-drawer.tsx
- Slide-in right drawer
- Shows full event details (из API)
- "Перейти к событию в Ленте" кнопка

## Deliverables
- `web_cabinet/ai/endpoints/ask_farm.py` (SSE endpoint)
- `web_cabinet/ai/prompts/ask_farm.py` (полный prompt, не skeleton)
- `web_cabinet/ai/session_memory.py`
- `web_app/components/ai/ask-farm-widget.tsx`
- `web_app/components/ai/evidence-chip.tsx`
- `web_app/components/ai/evidence-drawer.tsx`
- `web_app/lib/ai-client.ts`
- Интеграция в `web_app/app/(protected)/dashboard/page.tsx`
- `data/demo/investor_v1/preset_ai_answers.json`
- `docs/iterations/MVP-N13_execution_proof.md`

## Acceptance criteria
1. Widget виден на /dashboard
2. Preset "Почему упал удой у Звёздочки?" — отвечает за <3 сек (в demo-mode)
3. Ответ на русском с валидными evidence chips
4. Клик по chip → drawer открывается с event details
5. Free-form вопросы работают (медленнее, но работают)
6. Session memory: follow-up вопросы помнят контекст
7. Rate limit protection работает
8. Все CI гейты pass

## Формат ответа
Стандартный T34.
