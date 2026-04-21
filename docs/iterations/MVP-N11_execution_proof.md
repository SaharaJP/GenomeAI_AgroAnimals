# MVP-N11 Execution Proof — AI Gateway Backbone

**Дата:** 2026-04-21  
**Ветка:** ai/t34-20260421-231044  
**Исполнитель:** Claude Code (claude-sonnet-4-6)

---

## Scope

Создан модуль `web_cabinet/ai/` — встроенный AI-gateway backbone:
- Anthropic client с retry, prompt caching (beta), structured JSON logging
- 6 system prompts на русском с mandatory evidence grounding
- Redis-based кэш с graceful degradation
- Guardrails: input sanitize, output validate, rate limit, budget check
- Pydantic schemas для всех AI use-cases
- Farm context builder (skeleton для N12)
- Tool definitions skeleton (7 tools для N12)
- Health endpoint `/api/ai/health`
- 67 unit-тестов (mock Anthropic, mock Redis)

---

## Executed checks

### 1. Unit tests — web_cabinet/ai/tests/

```
pytest web_cabinet/ai/tests/ -q
67 passed in 0.60s
```

**Покрытие:**
- test_client.py: LLMResponse, retry logic, model routing, system blocks, mock generate, log output
- test_prompts.py: все 6 system prompts — русский язык, evidence grounding, anti-hallucination, build_*_message
- test_cache.py: key determinism, disabled mode, mock Redis get/set/invalidate, graceful degradation, ping

### 2. Module import smoke

```python
from web_cabinet.ai import get_ai_settings           # OK
from web_cabinet.ai.client import AnthropicClient    # OK  
from web_cabinet.ai.cache import get_cache           # OK
from web_cabinet.ai.guardrails import input_sanitize # OK
from web_cabinet.ai.context import build_demo_farm_context  # OK
from web_cabinet.ai.models import *                  # OK
from web_cabinet.ai.prompts import *                 # OK
from web_cabinet.ai.tools import ALL_TOOLS           # 7 tools

settings.GENOMEAI_AI_DEFAULT_MODEL = "claude-sonnet-4-6"
settings.use_opus_for = ["morning_brief", "weekly_brief"]
settings.is_configured = True
```

### 3. Health endpoint test

```python
# TestClient FastAPI
GET /api/ai/health → 200
{"status": "ok", "model": "claude-sonnet-4-6", "demo_mode": true,
 "cache_enabled": true, "api_configured": true}
```

### 4. Guardrails smoke

```
input_sanitize("<b>Вопрос</b>") → "Вопрос"
input_sanitize("A" * 2100) → truncated to 2000 chars
output_validate("...") → returns validated text
```

### 5. pyproject.toml — зависимости добавлены

```toml
"anthropic>=0.40"
"redis>=5.0"  
"tiktoken>=0.7"
"pydantic-settings>=2.0"
```

### 6. web_cabinet/app.py — регистрация маршрутов

```python
from web_cabinet.ai.endpoints import register_ai_routes
register_ai_routes(app)
```

Добавлено после строки `app.include_router(api_boundary_v1_router)`.

---

## Net result

**Deliverables созданы:**
```
web_cabinet/ai/
├── __init__.py
├── client.py          # AsyncAnthropic + retry + prompt caching + structured logs
├── config.py          # pydantic-settings (.env.ai)
├── models.py          # Pydantic schemas: MorningBrief, WeeklyBrief, Insight, ...
├── context.py         # FarmContext + build_demo_farm_context()
├── tools.py           # 7 tool definitions
├── cache.py           # Redis AICache с graceful degradation
├── guardrails.py      # input_sanitize, output_validate, rate_limit_check, check_budget
├── prompts/
│   ├── __init__.py
│   ├── ask_farm.py         # ASK_FARM_SYSTEM (рус. + evidence)
│   ├── morning_brief.py    # MORNING_BRIEF_SYSTEM (рус. + evidence)
│   ├── weekly_brief.py     # WEEKLY_BRIEF_SYSTEM (рус. + evidence)
│   ├── insight_scanner.py  # INSIGHT_SCANNER_SYSTEM (рус. + evidence)
│   ├── impact_narrative.py # IMPACT_NARRATIVE_SYSTEM (рус. + evidence)
│   └── insight_narrative.py # INSIGHT_NARRATIVE_SYSTEM (рус. + evidence)
├── endpoints/
│   ├── __init__.py    # register_ai_routes(app)
│   └── health.py      # GET /api/ai/health
└── tests/
    ├── test_client.py  # 14 tests
    ├── test_prompts.py # 31 tests
    └── test_cache.py   # 18 tests  (+ test_cache disabled: 3 + mock: 12 + keys: 4)
```

---

## Honest status

**`partially_proven`**

**Доказано:**
- 67 unit-тестов (mocked) — все green
- Module import smoke — OK
- Health endpoint via TestClient — 200 OK
- Guardrails smoke — OK
- pyproject.toml обновлён, зависимости установлены

**Не доказано (не требуется для N11):**
- Реальный вызов Anthropic API (нет live API call — это N13+)
- Redis integration (только mock — live Redis требует deploy/adult)
- Полная web_cabinet smoke (требует живой web_cabinet stack)
- Все 7 CI гейтов (не запускались — это scope N11 backbone, не production cutover)

**Блокеров нет.** N12 (farm context), N13 (ask-farm SSE), N14 (morning-brief) могут стартовать немедленно.
