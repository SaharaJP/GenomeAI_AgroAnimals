# MVP-N14 Execution Proof — Morning Brief Generator + Cron

## Scope

Реализация ежедневного утреннего брифинга ИИ-помощника:
- `POST /api/ai/morning-brief` — генерация / кэш-retrieval  
- `GET /api/ai/morning-brief/today` — для dashboard  
- `GET /api/ai/morning-brief/{id}/pdf` — PDF-экспорт  
- APScheduler cron 06:00 MSK в startup FastAPI  
- React-карточка на `/daily-summary` (первая позиция)  
- Demo-mode через `morning_briefs_seeded.json`  
- Alembic migration `20260422_05_morning_briefs`

---

## Delivered files

| Файл | Статус |
|------|--------|
| `web_cabinet/ai/models.py` | updated — добавлены `OvernightChange`, `TodayAction`, `MorningBriefRequest`, заменён `MorningBrief` |
| `web_cabinet/ai/prompts/morning_brief.py` | updated — новый структурированный prompt с JSON-схемой |
| `web_cabinet/ai/background/__init__.py` | created |
| `web_cabinet/ai/background/morning_brief_cron.py` | created — APScheduler, 06:00 MSK, CRON_TEST режим |
| `web_cabinet/ai/endpoints/morning_brief.py` | created — POST + GET endpoints, cache, demo mode, DB save |
| `web_cabinet/ai/endpoints/morning_brief_pdf.py` | created — reportlab + QR code |
| `web_cabinet/ai/endpoints/__init__.py` | updated — регистрация новых роутеров |
| `web_cabinet/app.py` | updated — `start_cron()` в `_startup()` |
| `src/core/migrations/alembic/versions/20260422_05_morning_briefs.py` | created |
| `data/demo/investor_v1/morning_briefs_seeded.json` | updated — новая схема V2 |
| `web_app/lib/api/morning-brief.ts` | created |
| `web_app/components/overview/morning-brief-card.tsx` | created |
| `web_app/app/(protected)/daily-summary/page.tsx` | updated — `<MorningBriefCard />` первым |
| `pyproject.toml` | updated — apscheduler>=3.10, qrcode>=8.0 |

---

## Executed checks

### 1. Python import smoke

```
python -c "from web_cabinet.ai.models import MorningBrief, OvernightChange, TodayAction, MorningBriefRequest; print('models OK')"
# → models OK

python -c "from web_cabinet.ai.prompts.morning_brief import MORNING_BRIEF_SYSTEM, build_morning_brief_message; from web_cabinet.ai.background.morning_brief_cron import get_active_farms; from web_cabinet.ai.endpoints import register_ai_routes; print('all imports OK')"
# → all imports OK
```

### 2. Seeded brief loading

```
python -c "from web_cabinet.ai.endpoints.morning_brief import _load_seeded_brief; ..."
# → brief_id: MBRIEF_20260422
# → headline: Требуется внимание: ночная активность Ночки критически низкая
# → actions: 4, changes: 3, notes: 3
```

### 3. Model construction

`MorningBrief` с `OvernightChange` + `TodayAction` конструируется без ошибок Pydantic.

### 4. Alembic migration syntax

Файл миграции соответствует паттерну предыдущих версий (`20260418_04_*`), `down_revision` указан корректно.

---

## Acceptance criteria — статус

| Критерий | Статус |
|----------|--------|
| POST /api/ai/morning-brief возвращает валидный JSON | `partially_proven` — импорты ок, demo-flow ок; runtime-прогон на поднятом сервере не выполнен |
| Cron triggers CRON_TEST=true через 1 минуту | `not_proven` — runtime не проверялся |
| /dashboard показывает brief card | `not_proven` — Next.js dev-сервер не запускался |
| Demo-mode показывает seeded brief | `proven` — unit-проверка `_load_seeded_brief` пройдена |
| PDF export работает | `partially_proven` — reportlab доступен (4.4.10), qrcode установлен; runtime PDF-response не проверялся |
| Evidence chips кликабельны | `not_proven` — UI не тестировался в браузере |
| Все CI гейты pass | `not_proven` — `bash scripts/run_ci_gate.sh` не запускался в этом инкременте |

---

## Risks / assumptions

- `psycopg2` для Postgres-save не является hard-dependency: `_save_to_db` работает с graceful fallback при отсутствии DSN.
- `apscheduler` установлен локально; добавлен в `pyproject.toml` для продакшн-образа.
- QR-код в PDF содержит хардкоженный domain `app.genomeai.ru` — в prod нужно параметризовать через env `GENOMEAI_APP_URL`.
- Cron `_generate_brief` запускается через `asyncio.new_event_loop()` из синхронного контекста APScheduler — безопасно в multithread-режиме FastAPI.
- `MorningBriefCard` — `'use client'` компонент; `daily-summary/page.tsx` стал Server Component-оберткой, что совместимо с App Router Next.js 15.

---

## Net result

**Status: `partially_proven`**

Baseline реализован: backend-модели, endpoints, cron, migration, demo-mode, frontend-карточка. Подтверждена корректность Python-импортов и demo-flow через unit-проверку. Runtime-прогон эндпоинтов, UI в браузере и CI гейты — не выполнялись в данном инкременте.

## От координатора

Для перевода в `proven`:
1. `uvicorn web_cabinet.app:app` — проверить `GET /api/ai/morning-brief/today`
2. `GENOMEAI_AI_CRON_TEST=true` — убедиться, что через 1 мин в логах `morning_brief generated ok`
3. `cd web_app && npm run dev` — проверить `/daily-summary` в браузере
4. `bash scripts/run_ci_gate.sh` — все 7 гейтов
