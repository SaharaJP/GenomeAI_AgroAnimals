# Задача MVP-N11: AI-gateway backbone (web_cabinet/ai/)

**PROMPT:**

## Контекст (обязательно прочитай)
- `CLAUDE.md`
- `.env.ai.example` — конфигурация AI
- `docs/strategy_overview.md` — зачем AI делаем не "для галочки"

## Цель
Создать модуль `web_cabinet/ai/` — встроенный AI-gateway для всех AI-фич MVP. НЕ отдельный сервис — именно модуль внутри web_cabinet (одна БД, один auth, один deploy).

## Структура

```
web_cabinet/ai/
├── __init__.py
├── client.py              # Anthropic wrapper с retry, caching, observability
├── models.py              # Pydantic схемы
├── context.py             # build_farm_context() — skeleton (расширяется в N12)
├── tools.py               # tool definitions (skeleton для N12)
├── prompts/
│   ├── __init__.py
│   ├── ask_farm.py
│   ├── morning_brief.py
│   ├── weekly_brief.py
│   ├── insight_scanner.py
│   ├── impact_narrative.py
│   └── insight_narrative.py
├── endpoints/
│   ├── __init__.py
│   └── (пока пусто — endpoints в N14, N15, N16, N17, N13)
├── cache.py               # Redis-based caching
├── guardrails.py          # input validation, output filtering
└── tests/
    ├── test_client.py
    ├── test_prompts.py
    └── test_cache.py
```

## Dependencies (в pyproject.toml добавить)
```
anthropic>=0.40
redis>=5.0
tiktoken>=0.7
```

## Регистрация в web_cabinet/app.py
```python
from web_cabinet.ai.endpoints import register_ai_routes
register_ai_routes(app)
```

## Ключевые файлы

### client.py
Единый AnthropicClient класс:
- Retry на transient errors (rate limit, timeouts)
- Prompt caching автоматически на system prompts и farm_context
- Observability: structured JSON logs (model, input_tokens, output_tokens, cache_hit, latency_ms, user_id)
- Методы: `generate(prompt, model, max_tokens, ...)`, `stream(...)`, `tool_call(...)`
- Model routing: если task_type в GENOMEAI_AI_USE_OPUS_FOR → opus, иначе default

### models.py
Pydantic schemas для всех endpoints:
- `MorningBrief`, `WeeklyBrief`, `Insight`, `ImpactAnalysis`, `AskFarmRequest/Response`, `AskFarmEvidence`
- Strict validation на output

### prompts/
Каждый файл — константа SYSTEM_PROMPT (str) + функция build_user_message(context) → str.
**ВСЕ промпты на русском** (см. принципы в `docs/strategy_overview.md`):
- ASK_FARM_SYSTEM, MORNING_BRIEF_SYSTEM, WEEKLY_BRIEF_SYSTEM, INSIGHT_SCANNER_SYSTEM, IMPACT_NARRATIVE_SYSTEM, INSIGHT_NARRATIVE_SYSTEM

Все требуют evidence grounding: "Каждое утверждение подкрепляй [evidence: event_xxx]".

### cache.py
Redis-based кэш:
- Key: hash(endpoint_name + json.dumps(params, sort_keys=True))
- TTL: из .env.ai (default 300s)
- Методы: `get()`, `set()`, `invalidate()`

### guardrails.py
- input_sanitize: max 2000 chars, strip HTML
- output_validate: check JSON schema, truncate если >2000 tokens
- rate_limit_check: через Redis (user_id + endpoint_name)
- check_budget: smoke-check не превысили monthly budget

## Конфигурация (из .env.ai)
Все вычитывается через pydantic-settings:
- ANTHROPIC_API_KEY (required)
- GENOMEAI_AI_DEFAULT_MODEL
- GENOMEAI_AI_OPUS_MODEL
- GENOMEAI_AI_HAIKU_MODEL
- GENOMEAI_AI_USE_OPUS_FOR (list)
- GENOMEAI_AI_ENABLE_CACHE
- GENOMEAI_AI_CACHE_TTL_SECONDS
- REDIS_URL
- GENOMEAI_AI_RATE_LIMIT_*
- GENOMEAI_AI_MONTHLY_BUDGET_USD
- GENOMEAI_AI_DEMO_MODE

## Endpoints в этом MVP не добавляем
Только backbone. Endpoints создаются в последующих задачах:
- N13: `/api/ai/ask-farm` (SSE)
- N14: `/api/ai/morning-brief`
- N15: insight_scanner (background, не endpoint)
- N16: `/api/ai/impact-narrative`
- N17: `/api/ai/weekly-brief`

## Принципы (ключ к "real assistant")

1. **Никаких "для галочки"**. Все AI responses — на основе real farm_context.
2. **Evidence grounding** всегда. LLM обязан подкреплять утверждения event_id из контекста.
3. **Русский язык** строго. В system prompt явно.
4. **No hallucinations** — в output_validate отфильтровать claims без valid evidence.
5. **Structured output** — все ответы в Pydantic schemas, не свободный текст.

## Тесты
- test_client: mock Anthropic, проверяем retry и caching
- test_prompts: проверяем что все system prompts требуют evidence и русский
- test_cache: Redis integration (через docker-compose test)

## Deliverables
- Вся структура `web_cabinet/ai/` создана
- 6 prompts на русском с evidence requirements
- pyproject.toml обновлён
- Tests pass (unit + mocked integration)
- Альфа-endpoint `/api/ai/health` возвращает `{"status": "ok", "model": "..."}` для smoke test
- `docs/iterations/MVP-N11_execution_proof.md`

## Acceptance criteria
1. `pytest web_cabinet/ai/tests/` — все pass
2. `curl http://localhost:8000/api/ai/health` → 200 OK
3. Ручной тест client.py:
   ```python
   from web_cabinet.ai.client import AnthropicClient
   client = AnthropicClient()
   response = client.generate("Ответь на русском: что такое молочная ферма?", max_tokens=100)
   assert "молочная" in response.lower()
   ```
4. Все 7 CI гейтов pass
5. Не ломает существующий web_cabinet smoke

## Формат ответа
Стандартный T34.
