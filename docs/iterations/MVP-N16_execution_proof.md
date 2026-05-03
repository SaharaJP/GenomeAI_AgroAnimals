# MVP-N16 Impact Narrative Generator — Execution Proof

**Date:** 2026-04-23T08:31:13Z  
**Branch:** ai/t34-20260423-111451  
**Executor:** Claude Sonnet 4.6 (AI developer)  
**Status:** `partially_proven` — runtime-доказательство: pytest 31+67=98 тестов прошли; LLM-вызов и Redis-кэш не гонялись на живом контуре (нет Anthropic API key + Redis в окружении)

---

## Scope

Реализован полный backend + frontend для `POST /api/ai/impact-narrative` (MVP-N16).  
Endpoint принимает `event_id + window + farm_id`, возвращает `ImpactNarrative` с narrative,  
interpretation, significance, recommendations, confidence.

Demo-режим: seeded narratives для 8 главных demo-событий (TL_001–TL_008).  
Production-режим: Claude Sonnet 4.6 с IMPACT_NARRATIVE_SYSTEM промптом, кэш Redis 24ч.

---

## Deliverables

| Файл | Статус | Описание |
|------|--------|----------|
| `web_cabinet/ai/models.py` | ✅ изменён | Добавлены `ImpactNarrativeRequest`, `ImpactNarrative` |
| `web_cabinet/ai/prompts/impact_narrative.py` | ✅ переписан | Полный IMPACT_NARRATIVE_SYSTEM промпт, новый `build_impact_narrative_message()` |
| `web_cabinet/ai/endpoints/impact_narrative.py` | ✅ создан | `POST /api/ai/impact-narrative`, demo + production path, кэш 24ч |
| `web_cabinet/ai/endpoints/__init__.py` | ✅ изменён | Зарегистрирован `impact_narrative_router` |
| `data/demo/investor_v1/seeded_impact_narratives.json` | ✅ создан | 8 seeded narratives для TL_001–TL_008 |
| `web_app/lib/api/impact-narrative.ts` | ✅ создан | TypeScript API-клиент: типы + `fetchImpactNarrative()` |
| `web_app/components/timeline/impact-narrative-section.tsx` | ✅ создан | React-компонент с бирюзовой полосой, badge, recommendations |
| `web_app/components/timeline/impact-panel.tsx` | ✅ создан | Impact Panel с WindowSelector, MetricCards, AI-секцией |
| `tests/test_impact_narrative.py` | ✅ создан | 31 тест (mock Claude, parse, seeded, cache, classification) |
| `web_cabinet/ai/tests/test_prompts.py` | ✅ исправлен | Обновлена подпись `build_impact_narrative_message()` |
| `tests/conftest.py` | ✅ исправлен | Добавлен evict web_cabinet из sys.modules для корректного импорта |

---

## Executed Checks

### 1. pytest — tests/test_impact_narrative.py (31 тест)

```
31 passed in 0.86s
```

Покрытие:
- `TestImpactNarrativeModel` (5 тестов) — Pydantic-валидация, confidence bounds, literals
- `TestImpactNarrativeRequest` (3 теста) — defaults, window literals, invalid window
- `TestPromptBuilder` (3 теста) — system prompt rules, message builder format, JSON validity
- `TestParseResponse` (4 теста) — valid JSON, markdown fence strip, invalid JSON error, defaults
- `TestSeededNarratives` (7 тестов) — file exists, valid JSON, required fields, parse to model, seeded load, fallback, 2-3 sentences, 8 events coverage
- `TestCacheLogic` (2 теста) — cache hit skips LLM, cache miss calls seeded + sets cache
- `TestClassification` (7 тестов) — mastitis negative/major, culling negative/major, heat positive, calving positive, recommendations present, major events confidence ≥0.85

### 2. pytest — web_cabinet/ai/tests/ (67 тестов)

```
67 passed in 1.08s
```

Включает test_prompts.py — обновлённый тест `test_impact_narrative_includes_event` проходит с новой сигнатурой.

### 3. Совместный прогон

```
98 passed in 1.31s
```

### 4. Demo seeded data — ручная проверка

Все 8 narratives (TL_001–TL_008):
- narrative: 2-3 предложения ✅
- interpretation: negative/positive корректно для типовых кейсов ✅
- significance: major для мастита, выбраковки, SCC-алертов ✅
- recommendations: 3 конкретных actionable пункта ✅
- confidence: ≥0.85 для major events ✅

### 5. Import chain — ручная проверка

```bash
python -c "import sys; sys.path.insert(0,'.'); from web_cabinet.ai.models import ImpactNarrative; print('OK')"
# OK
python -c "import sys; sys.path.insert(0,'.'); from web_cabinet.ai.endpoints.impact_narrative import generate_impact_narrative; print('OK')"
# OK
```

### 6. Endpoint schema — проверка маршрутизации

```python
from web_cabinet.ai.endpoints import register_ai_routes
# impact_narrative_router включён в register_ai_routes
```

---

## Not Proven (runtime-доказательства нет)

| Элемент | Статус | Причина |
|---------|--------|---------|
| `POST /api/ai/impact-narrative` HTTP-ответ | `not_proven` | Нет живого сервера в CI-контуре |
| Redis кэш (< 50ms второй запрос) | `not_proven` | Redis недоступен в текущем окружении |
| Claude Sonnet LLM-вызов и парсинг ответа | `not_proven` | ANTHROPIC_API_KEY не настроен |
| Frontend рендеринг Impact Panel в браузере | `not_proven` | Next.js dev server не запущен |
| 7 CI-гейтов (`scripts/run_ci_gate.sh` и пр.) | `not_proven` | CI не был запущен в worktree-контуре |

---

## Risks / Assumptions

1. **`web_cabinet.ai` import path**: В worktree существует проблема — `web_cabinet` кэшируется из другого расположения до загрузки conftest.py. Фикс: evict `web_cabinet` из `sys.modules` в `tests/conftest.py` и явно в `tests/test_impact_narrative.py`. Это рабочий workaround, но корневая причина — конфликт editable install и worktree без переустановки пакета.

2. **LLM-парсинг**: Реализован `_parse_response()` с graceful defaults; если LLM вернёт не-JSON — будет `ValueError`, endpoint вернёт 500. Рекомендуется добавить retry с simplified prompt при первой ошибке парсинга.

3. **before/after metrics**: В текущей реализации `_compute_window_metrics()` берёт данные из `impact_analyses_seeded.json` только для seeded event_id. Для production нужна интеграция с реальной БД (TODO).

4. **Frontend**: Компоненты `impact-panel.tsx` и `impact-narrative-section.tsx` созданы, но TypeScript-компиляция и рендеринг в браузере не проверены (нет CI для Next.js в worktree).

---

## От координатора

Необходимо для `proven`:
1. Запустить `bash scripts/run_ci_gate.sh` на живом контуре с Redis + API key
2. Поднять `uvicorn web_cabinet.app:app` и выполнить `curl -X POST /api/ai/impact-narrative -d '{"event_id":"TL_001","window":"4w"}'`
3. Проверить кэш: второй идентичный запрос должен вернуться < 100ms
