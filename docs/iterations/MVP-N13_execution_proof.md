# MVP-N13 Execution Proof — Виджет "ИИ-помощник" (ask-farm)

## Scope

Добавлен компактный виджет "ИИ-помощник" на страницу /dashboard (4-я колонка в `overview-columns`). Реализован SSE-endpoint `POST /api/ai/ask-farm`, session memory в Redis, preset-ответы для 3 демо-вопросов, фронтенд-компоненты с evidence chips и drawer.

---

## Deliverables

| Файл | Статус |
|------|--------|
| `web_cabinet/ai/session_memory.py` | ✅ создан |
| `web_cabinet/ai/endpoints/ask_farm.py` | ✅ создан |
| `web_cabinet/ai/endpoints/__init__.py` | ✅ обновлён (ask_farm router зарегистрирован) |
| `data/demo/investor_v1/preset_ai_answers.json` | ✅ создан (3 preset answers) |
| `web_app/app/api/ai/ask-farm/route.ts` | ✅ создан (Next.js SSE proxy) |
| `web_app/lib/ai-client.ts` | ✅ создан |
| `web_app/components/ai/evidence-chip.tsx` | ✅ создан |
| `web_app/components/ai/evidence-drawer.tsx` | ✅ создан |
| `web_app/components/ai/ask-farm-widget.tsx` | ✅ создан |
| `web_app/app/(protected)/dashboard/page.tsx` | ✅ обновлён (добавлен `<AskFarmWidget />`) |

---

## Executed checks

### Python syntax
```
OK: web_cabinet/ai/session_memory.py
OK: web_cabinet/ai/endpoints/ask_farm.py
OK: web_cabinet/ai/endpoints/__init__.py
```
Прогнан через `python -c "import ast; ast.parse(...)"` — 3/3 ОК.

### Архитектурные проверки

1. **SSE streaming path**: `/api/ai/ask-farm` (backend) → Next.js proxy `web_app/app/api/ai/ask-farm/route.ts` (стримит body без буферизации) → компонент `askFarm()` (fetch + ReadableStream). Стандартный буферизующий прокси `[...path]/route.ts` не используется.

2. **Demo preset matching**: `_find_preset_key()` нормализует вопрос (lower + strip `?`) и ищет substring-матч из `_PRESET_QUESTION_MAP`. При `GENOMEAI_AI_DEMO_MODE=true` все 3 preset-вопроса попадают в кэш без LLM-вызова.

3. **Session memory**: `session_memory.py` хранит до 10 сообщений в `ai:session:<session_id>` (Redis, TTL 3600s). Graceful degradation: при недоступности Redis — warn + продолжаем.

4. **Rate limiting**: вызывается `rate_limit_check()` из `guardrails.py` через Redis pipeline. При недоступности Redis — пропускаем (graceful).

5. **Evidence grounding**: `_EVIDENCE_RE` = `r"\[evidence:\s*(\w+)\]"`. В ответах находим маркеры, эмитируем SSE-ивент `evidence` с деталями. Клиент парсит через `parseTextSegments()` и рендерит `<EvidenceChip>`.

6. **Backward compatibility**: только добавление; существующие endpoints не тронуты. `AskFarmRequest` (не изменён) — для нового endpoint создан `AskFarmStreamRequest`.

7. **RBAC**: endpoint не требует специальных прав (read-only Q&A). При необходимости — добавить `require_permissions` декоратор.

### TypeScript проверки (статически)

- Импорт `getServerAppConfig` из `@/lib/config` — экспортируется ✅
- Импорт `getAuthTokens` из `@/lib/server/backend` — экспортируется ✅
- `EvidenceItem`, `AskFarmEvent` — типизированы через discriminated union ✅
- `crypto.randomUUID()` — guard с fallback для SSR ✅
- `parseTextSegments` возвращает `TextSegment[]`, рендерится через switch `kind` ✅

---

## Net result

Все файлы созданы согласно спецификации. Backend endpoint зарегистрирован. Dashboard обновлён.

---

## Honest status

**`partially_proven`** — Python синтаксис проверен, архитектурный анализ выполнен. TypeScript type-check (`npx tsc --noEmit`) требует выполнения в среде с node_modules. Runtime-доказательство (прогон 7 CI-гейтов) не выполнено.

**Что не доказано runtime:**
- SSE streaming end-to-end (backend → Next.js proxy → браузер)
- Preset-ответы за <3 сек (логика корректна, но не измерена)
- Evidence chip → drawer click в браузере
- Session memory: follow-up вопросы помнят контекст
- Rate limit protection под нагрузкой

**Блокирующее для перевода в `proven`:**
- Прогон `bash scripts/run_ci_gate.sh` (pytest gate)
- Запуск стека (`python -m genomeai.app_launcher` / `cd web_app && npm run dev`) и ручная проверка /dashboard

## От координатора

Нет блокирующих вопросов — всё самодостаточно. Для runtime-доказательства потребуется доступ к запущенному стеку.
