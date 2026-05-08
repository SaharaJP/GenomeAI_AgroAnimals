---
title: "P0-1: AI Observability Admin Panel — Design"
date: 2026-05-09
author: server Claude (T34 dev context)
source_brief: docs/THESIS_ALIGNMENT_BRIEF_2026-05-08.md (§P0-1)
thesis_anchor: "§3.1.7 Observability MVP"
status: approved
---

# P0-1: AI Observability Admin Panel — Design Specification

## Цель

Реализовать раздел `/admin/ai` для роли Admin как MVP-уровня AI-наблюдаемости (§3.1.7 ВКР, Phase 1). Защищающемуся это даёт демонстрируемый foundation для будущей миграции на Langfuse + Prometheus.

## Acceptance criteria (из брифинга §P0-1)

- Логин под `admin`/`admin`, переход на `/admin/ai`, видна сводка с непустыми числами после хотя бы одного вызова `/api/ai/morning-brief`.
- Для пользователя без роли `Admin` страница возвращает 403.
- Снимок Playwright `admin_ai_dashboard.png` приложен в коммит.
- Endpoint `/api/admin/ai/stats` отвечает <200 мс на p50.

## Scope

### В P0-1 включено
- 5 виджетов: stats summary (4 карточки), grounding rate, ручные триггеры (2 кнопки), таблица последних 100 вызовов, drawer с trace вызова.
- Persistent storage: новая таблица `ai_call_log` в Postgres + best-effort вставка из `web_cabinet/ai/client.py`.
- 4 backend endpoint под `/api/admin/ai/*`.
- Pricing module `web_cabinet/ai/pricing.py` (статические цены Anthropic, дата ревизии в комментарии).
- Russian UI.

### Явно НЕ в P0-1 (отнесено в P0-1.5)
- Cost-trend widget (7-дневный график).
- Tools-health widget (агрегация по `tools_used` JSONB).
- Retention cron (удаление записей >30 дней).
- Backfill из исторических логов в файлах.

Поле `tools_used` JSONB пишется уже в P0-1, чтобы P0-1.5 не требовал новой миграции.

## Архитектура

```
LLM call (web_cabinet/ai/client.py)
  ├─ (existing) logger.info({event: "llm_call", ...})
  └─ (NEW) asyncio.create_task(insert_ai_call_log(...))
              ↓ try/except — never breaks AI flow
         Postgres: ai_call_log
              ↑
       /api/admin/ai/* (require_permissions("audit.view"))
              ↑
       Next.js /admin/ai (Russian UI)
```

**Ключевое решение:** добавление best-effort async-вставки в hot path AI-вызовов. Стоимость ~2–5 мс на вызов; ошибки записи перехватываются в `try/except` и логируются, но не пробрасываются — таким образом нарушение БД не валит AI flow.

## Storage: таблица `ai_call_log`

Миграция: `src/core/migrations/alembic/versions/20260509_14_ai_call_log.py`

```sql
CREATE TABLE ai_call_log (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id       VARCHAR(64),                  -- nullable для cron-задач
    endpoint      VARCHAR(64) NOT NULL,         -- 'morning-brief', 'ask-farm', ...
    task_type     VARCHAR(32) NOT NULL,         -- 'default', 'opus', 'haiku'
    model         VARCHAR(64) NOT NULL,

    -- token economics
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
    cost_usd              NUMERIC(10, 6) NOT NULL DEFAULT 0,

    -- timing & status
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    error         TEXT,                         -- non-null = failed call

    -- trace
    prompt        TEXT,                         -- user_message, capped 50KB
    response      TEXT,                         -- response.content, capped 50KB
    evidence_chips JSONB,                       -- list[str]
    tools_used    JSONB                         -- list[{name, args, latency_ms}]
);

CREATE INDEX ix_ai_call_log_created_at ON ai_call_log (created_at DESC);
CREATE INDEX ix_ai_call_log_endpoint   ON ai_call_log (endpoint);
CREATE INDEX ix_ai_call_log_user_id    ON ai_call_log (user_id);
```

**Capping policy:** `prompt` и `response` обрезаются до 50 КБ. Усечённые значения снабжаются префиксом `[TRUNCATED:<original_size_kb>kb]\n` в начале строки.

**Downgrade:** удалить индексы и таблицу. Обязательно протестировать `alembic downgrade -1` + `upgrade head`.

## Pricing module

Файл: `web_cabinet/ai/pricing.py`

```python
# Anthropic pricing per million tokens, USD; verified 2026-05.
# Revisit quarterly via https://www.anthropic.com/pricing
PRICES_USD_PER_MTOK = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_create": 3.75},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.00, "cache_read": 1.50, "cache_create": 18.75},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00,  "cache_read": 0.10, "cache_create": 1.25},
}

def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Возвращает стоимость вызова в USD. Неизвестная модель → 0.0 (не валим)."""
```

Тест: `tests/web_cabinet/ai/test_pricing.py` — happy path для всех 3 моделей + неизвестная модель → 0.

## Backend endpoints

Все под `/api/admin/ai/*`, gate `require_permissions("audit.view")`. Новый модуль `web_cabinet/admin/ai_observability.py` (router) + регистрация в `web_cabinet/app.py`.

### `GET /api/admin/ai/stats?period_hours=24`

Параметры: `period_hours ∈ {1, 24, 168}` (дефолт 24).

Response:
```json
{
  "period_hours": 24,
  "count": 237,
  "p50_latency_ms": 850,
  "p95_latency_ms": 1820,
  "total_input_tokens": 145000,
  "total_output_tokens": 28000,
  "total_tokens": 173000,
  "total_cost_usd": 1.34,
  "error_count": 3,
  "error_rate": 0.0127
}
```

SQL: одиночный `SELECT … FROM ai_call_log WHERE created_at >= NOW() - INTERVAL '<n> hours'` с `percentile_cont` для латенции. Таргет p50 < 200 мс при индексе на `created_at`.

### `GET /api/admin/ai/calls?limit=100&endpoint=&user_id=&status=`

Параметры:
- `limit` ∈ [1, 500], default 100
- `endpoint` — точное совпадение, optional
- `user_id` — точное совпадение, optional
- `status` ∈ {`ok`, `error`}, optional

Response: `[{id, created_at, endpoint, model, user_id, latency_ms, total_tokens, cost_usd, has_error}]`. Поля `prompt` и `response` намеренно опущены (для скорости таблицы).

### `GET /api/admin/ai/calls/{call_id}`

Response: полная запись из `ai_call_log` (все поля).

404 если `call_id` не найден.

### `GET /api/admin/ai/grounding-rate?period_hours=24`

Response:
```json
{
  "period_hours": 24,
  "with_evidence": 216,
  "without_evidence": 21,
  "total": 237,
  "rate_pct": 91.14
}
```

Логика: `WHERE jsonb_array_length(evidence_chips) > 0`.

### Кнопки в UI

Не требуют новых endpoint — UI вызывает существующие:
- `POST /api/ai/morning-brief`
- `POST /api/ai/insights/scan-now`

## Frontend

### Файлы

- `web_app/app/(protected)/admin/ai/page.tsx` — route entry
- `web_app/components/admin/ai-observability.tsx` — основной компонент
- `web_app/components/admin/ai-call-trace-drawer.tsx` — drawer с полным trace
- `web_app/lib/api/admin-ai.ts` — типизированный API client

### Layout (Russian copy)

```
┌─ Admin / AI-наблюдаемость ─────────────────────────────────────┐
│                                                                │
│ Period: [1ч] [24ч*] [7д]                                       │
│                                                                │
│ ┌──────────┬──────────┬──────────┬──────────┐                  │
│ │ Вызовов  │ p95      │ Токенов  │ Стоимость│                  │
│ │ 237      │ 1.8 c    │ 412 K    │ $1.34    │                  │
│ └──────────┴──────────┴──────────┴──────────┘                  │
│                                                                │
│ ┌─ Grounding rate ──┐  ┌─ Ручные триггеры ────────────────┐    │
│ │  91.2%            │  │ [Сгенерировать утренний брифинг] │    │
│ │  216 / 237 ✓      │  │ [Сканировать инсайты сейчас]     │    │
│ └───────────────────┘  └──────────────────────────────────┘    │
│                                                                │
│ ┌─ Последние 100 вызовов ─────────────────────────────────┐    │
│ │ [endpoint ▼] [user ▼] [status ▼]                        │    │
│ │ │ id │ время │ endpoint │ model │ latency │ tokens │ ✓  │    │
│ │ ... rows, click → trace drawer ...                      │    │
│ └─────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
```

Drawer (slide-in, ширина ~640px):
- Заголовок: `Trace #<id>` + время + endpoint
- Метрики (3 строки): latency / tokens / cost
- System prompt (truncated preview, expand on click)
- User message (full, monospace)
- Response (markdown rendered)
- Evidence chips (list)
- Tools used timeline

### 403 handling

Server-side: middleware/route guard проверяет `permissions` пользователя; если нет `audit.view` или `users.manage` → возвращает 403.

Client-side: на 403 рендерится плашка «Нет прав доступа».

## Тестирование

### Pytest

- `tests/web_cabinet/ai/test_pricing.py` — math для 3 моделей + unknown.
- `tests/web_cabinet/admin/test_ai_observability.py`:
  - 403 для не-Admin (no `audit.view`)
  - 200 + правильный JSON shape для Admin
  - stats math на синтетических данных (10 записей, проверить count, p50, p95, total_cost)
  - grounding-rate calculation
  - calls filter by endpoint/user/status
- Мини-fixture: вставка ~10 записей в `ai_call_log` через factory.

### Migration

```bash
alembic -c alembic.ini upgrade head
alembic -c alembic.ini downgrade -1
alembic -c alembic.ini upgrade head  # idempotency
```

### Playwright e2e (positive)

1. Login admin/admin
2. Goto `/admin/ai`
3. Click «Сгенерировать утренний брифинг» → wait for HTTP 200
4. Reload → видны числа > 0 в карточках
5. Click первой строки таблицы → drawer открыт, видны prompt + response
6. Screenshot `admin_ai_dashboard.png`
7. Screenshot `admin_ai_call_trace.png`

### Playwright e2e (negative)

1. Login обычного user (без `audit.view`)
2. Goto `/admin/ai` → видна плашка «Нет прав доступа» / 403

## Best-effort logging hook

В `web_cabinet/ai/client.py` после `logger.info(record)`:

```python
async def _persist_ai_call(record, prompt, response, evidence_chips, tools_used):
    try:
        async with get_async_db() as conn:
            cost = compute_cost_usd(record["model"], ...)
            await conn.execute(
                "INSERT INTO ai_call_log (...) VALUES (...)",
                ...
            )
    except Exception as e:
        logger.warning("ai_call_log insert failed: %s", e)

# в hot path:
asyncio.create_task(_persist_ai_call(...))
```

В sync-контексте (`generate()` без async) — использовать sync DB cursor, по той же best-effort семантике.

## Риски и допущения

1. **Async insert latency:** ~2–5 мс. Принято.
2. **prompt/response размер:** capped 50 КБ.
3. **PII:** имена коров и метрики стада в prompt. Mitigation: admin-only доступ; retention в P0-1.5.
4. **Цены моделей стареют:** документирована дата ревизии и квартальный пересмотр.
5. **`tools_used` сбор:** требуется доработка `ask_farm.py` agent loop для записи списка вызванных tools — +30 мин.
6. **Параллелизм:** при пике AI-нагрузки `create_task` создаёт unbounded set задач. Принято для MVP — нагрузка низкая на демо-ферме.

## Что меняется в существующих файлах

- `web_cabinet/ai/client.py`: расширение `_log_call` + новая функция `_persist_ai_call`.
- `web_cabinet/ai/endpoints/ask_farm.py`: сбор `tools_used` для записи (если ещё не собирается).
- `web_cabinet/app.py`: регистрация нового router.
- `web_app/app/(protected)/admin/page.tsx` (Admin Command Center): добавить ссылку «AI-наблюдаемость».

## Что создаётся новое

- `src/core/migrations/alembic/versions/20260509_14_ai_call_log.py`
- `web_cabinet/ai/pricing.py`
- `web_cabinet/admin/ai_observability.py` (router + handlers)
- `web_app/app/(protected)/admin/ai/page.tsx`
- `web_app/components/admin/ai-observability.tsx`
- `web_app/components/admin/ai-call-trace-drawer.tsx`
- `web_app/lib/api/admin-ai.ts`
- `tests/web_cabinet/ai/test_pricing.py`
- `tests/web_cabinet/admin/test_ai_observability.py`

## Коммит-стратегия (CLAUDE.md §3)

Согласно правилу «миграция + код + golden» отдельно:
1. **Commit 1:** alembic migration `20260509_14_ai_call_log.py` (только миграция)
2. **Commit 2:** backend (pricing, observability router, client logging hook, tests)
3. **Commit 3:** frontend (page, components, API client, Playwright proof)

Golden update **не требуется** (нет изменений в публичных контрактах CLI/golden scenarios).

## 7-gate verification

После всех 3 коммитов прогнать стандартный набор:
1. `bash scripts/run_ci_gate.sh`
2. `python -m web_cabinet.smoke ...`
3. `genomeai verify_refactor ...`
4. `bash scripts/run_warning_governance_gate.sh`
5. `bash scripts/run_operational_rollout_gate.sh`
6. `bash scripts/run_competitive_acceptance_gate.sh`
7. `bash scripts/run_perf_gates.sh`

Артефакты в `artifacts/_ci/` + proof-файл `docs/iterations/T34-P0-1_execution_proof.md` по шаблону §2 CLAUDE.md.

## Время

- Migration + pricing + tests: ~1 ч
- Backend endpoints + best-effort hook: ~1.5 ч
- Frontend page + drawer + API client: ~1.5 ч
- Playwright + 7 gates + proof file: ~1 ч

**Итого: ~5 ч.**
