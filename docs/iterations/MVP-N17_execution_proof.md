# MVP-N17 Weekly Brief Full Generator — Execution Proof

**Date:** 2026-04-23  
**Branch:** ai/t34-20260423-224413  
**Status:** partially_proven (demo+unit proven; production LLM call not runtime-proven — no live API key in CI)

---

## Scope

Полноценный еженедельный farm briefing: AI генерирует развёрнутый отчёт за диапазон дат с трендами, аномалиями, 5+ рекомендациями.

---

## Executed checks

### 1. Unit / integration tests
```
tests/test_weekly_brief.py — 43 passed, 0 failed, 25 warnings (deprecation-only)
Runtime: 1.07s
```

Покрыто:
- Pydantic-валидация WeeklyBrief, WeeklyBriefRequest, BriefSection, KeyRecommendation, Anomaly, DateRange
- `_parse_response`: полный, minimal, markdown-fence strip, invalid JSON
- Seeded data: 3 записи, ≥3 секций каждая, ≥3 рекомендаций, kpi_table, period fields
- Demo mode: exact period match, fallback to first record, cache set
- Cache logic: cache hit skips generation, force_regenerate bypasses cache
- Cron: imports ok, lifecycle, get_active_farms
- Acceptance criteria AC1-AC4, AC6

### 2. Файлы созданы/изменены
```
web_cabinet/ai/models.py                              — добавлены DateRange, BriefSection, KeyRecommendation, Anomaly, WeeklyBriefRequest; WeeklyBrief обновлён
web_cabinet/ai/prompts/weekly_brief.py               — расширен WEEKLY_BRIEF_SYSTEM, обновлён build_weekly_brief_message
web_cabinet/ai/endpoints/weekly_brief.py             — NEW: POST /api/ai/weekly-brief, GET /api/ai/weekly-brief/latest
web_cabinet/ai/endpoints/weekly_brief_pdf.py         — NEW: GET /api/ai/weekly-brief/{id}/pdf
web_cabinet/ai/background/weekly_brief_cron.py       — NEW: APScheduler 07:00 MSK Monday
web_cabinet/ai/endpoints/__init__.py                 — зарегистрированы weekly_brief + weekly_brief_pdf роутеры
web_cabinet/app.py                                   — start/stop weekly_brief cron в lifespan
web_cabinet/templates/email/weekly_brief.html.j2     — NEW: Jinja2 email template
data/demo/investor_v1/weekly_briefs_seeded.json      — расширено до 3 полных записей с полной структурой
src/core/migrations/alembic/versions/20260423_06_weekly_briefs.py — NEW: таблица weekly_briefs
web_app/lib/api/weekly-brief.ts                      — NEW: TypeScript types + fetch/generate/pdfUrl
web_app/components/overview/weekly-brief-card.tsx    — NEW: React компонент с коллапсными секциями
web_app/app/(protected)/weekly-brief/page.tsx        — NEW: страница /weekly-brief
tests/test_weekly_brief.py                           — NEW: 43 теста
```

---

## Net result

| Acceptance Criteria | Статус |
|---|---|
| AC1: POST /api/ai/weekly-brief возвращает WeeklyBrief | proven (unit + demo) |
| AC2: Narrative на русском с evidence | proven (unit AC2 pass) |
| AC3: Минимум 3 sections | proven (seeded 4 секции) |
| AC4: 3-7 recommendations с rationale | proven (unit AC4 pass) |
| AC5: PDF export корректный | partially_proven (код написан, runtime не проверен без reportlab) |
| AC6: Demo-mode instant | proven (< 1s, unit AC6 pass) |
| AC7: CI gates pass | not_proven (только test_weekly_brief.py запущен) |

---

## Honest status

**partially_proven**

Доказано runtime-прогоном:
- 43 unit/integration теста 100% green
- Demo mode (seeded data) — fully proven: exact period match, fallback, cache, model validation
- Python models, prompts, parse_response, cron lifecycle
- TypeScript types + API lib (static, no TS check run in this increment)

Не доказано (требует live контура):
- Production LLM call (Claude Opus 4.7) — нет API key в CI
- PDF export (reportlab runtime)
- Email delivery (SMTP stub, только log)
- DB save (Postgres DSN не доступен в CI)
- Frontend рендеринг (Next.js не запущен)
- Full 7-gate CI (только test_weekly_brief.py прогнан)

---

## Risks / assumptions

1. `reportlab` должен быть установлен для PDF — в dev/prod окружении есть
2. APScheduler timezone `Europe/Moscow` — требует `pytz` (уже есть в зависимостях)
3. Email template — Jinja2 stub, реальный SMTP не реализован (planned follow-up)
4. Frontend: TypeScript типы верны статически, но TS compile check не запускался
5. Alembic migration: `down_revision` указывает на `20260422_05_morning_briefs` — требует проверки на боевом Alembic

## От координатора

Требуется для перевода в `proven`:
1. Прогон `bash scripts/run_ci_gate.sh` на контуре с Postgres/Redis
2. Проверка `GET /api/ai/weekly-brief/latest` с живым сервером (curl-тест)
3. Проверка `GET /api/ai/weekly-brief/{id}/pdf` (curl → file.pdf)
4. Подтверждение что Alembic migration применяется без конфликтов
