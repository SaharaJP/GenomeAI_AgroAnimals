# Задача MVP-N14: Morning brief generator + cron

**PROMPT:**

## Контекст
- AI-gateway: MVP-N11
- Farm context: MVP-N12
- Overview UI: MVP-N02

## Цель
Ежедневный утренний брифинг ИИ-помощника. Cron 06:00 MSK. Отображается на /dashboard как первая карточка.

## Backend

### POST /api/ai/morning-brief

Request: `{"farm_id": "demo-farm-v1", "force_regenerate": false}`

Response (Pydantic MorningBrief):
```python
class MorningBrief(BaseModel):
    brief_id: str
    farm_id: str
    generated_at_utc: datetime
    date: date
    
    headline: str  # "Спокойное утро" / "Требуется внимание к группе 3" / "Критично: эпизод мастита"
    main_takeaway: str  # 2-3 предложения с evidence
    
    overnight_changes: list[OvernightChange]
    today_actions: list[TodayAction]
    notes: list[str]
    
    generation_model: str
    generation_tokens: dict  # {input, output}

class OvernightChange(BaseModel):
    text: str  # "Удой Звёздочки упал на 2.1 кг за ночь [evidence: event_...]"
    evidence_id: str | None

class TodayAction(BaseModel):
    action: str
    priority: Literal["high", "medium", "low"]
    due: str | None  # "до 14:00"
    role: Literal["vet", "zootech", "operator", "director"]
```

### Логика
1. Check cache (today's brief exists?) → return unless force_regenerate
2. build_farm_context() с period_days=1 (смотрим на последние 24 часа)
3. Claude Opus 4.7 (высокое качество для morning brief)
4. System prompt: MORNING_BRIEF_SYSTEM (жёсткие правила, русский, evidence)
5. Parse response → MorningBrief pydantic
6. Validate evidence_ids
7. Save в Postgres table `morning_briefs`
8. Cache в Redis

## Cron

### Реализация: APScheduler в web_cabinet startup
Или systemd timer (в зависимости от предпочтений инфраструктуры).

### Задача
- Запуск: 06:00 MSK каждый день
- Для активной фермы: trigger generation
- Log результат

```python
# web_cabinet/ai/background/morning_brief_cron.py
from apscheduler.schedulers.background import BackgroundScheduler

def run_daily_morning_brief():
    for farm in get_active_farms():
        try:
            generate_morning_brief(farm.id)
        except Exception as e:
            log.error(f"morning_brief failed for {farm.id}", exc_info=e)

scheduler = BackgroundScheduler(timezone="Europe/Moscow")
scheduler.add_job(run_daily_morning_brief, 'cron', hour=6, minute=0)
```

### Регистрация в app.py startup
```python
@app.on_event("startup")
async def startup_event():
    from web_cabinet.ai.background.morning_brief_cron import scheduler
    if os.getenv("GENOMEAI_AI_CRON_ENABLED", "true").lower() == "true":
        scheduler.start()
```

## Frontend

### components/overview/morning-brief-card.tsx
Занимает верхнюю часть /dashboard (вместо "Требует вашего внимания" empty state).

Layout:
- Small label "ИИ-помощник • обновлено 4 часа назад"
- Headline (крупным шрифтом)
- Main takeaway (2-3 предложения)
- Expandable sections:
  - "Что изменилось за ночь" (bullet list с evidence chips)
  - "Требует внимания сегодня" (actions с priority badges)
  - "На заметку" (collapsed by default)
- Footer actions: [🔄 Обновить] [📄 PDF] [🔊 Прослушать (stub)]

Если brief = `null` (ещё не сгенерирован):
- Empty state "Брифинг будет готов в 06:00" + button [Сгенерировать сейчас]

### Интеграция
Заменяет существующий `AttentionCard` из MVP-N02 (или может работать вместе — если brief есть, показывается он; если нет — fallback на AttentionCard).

## Demo mode
В demo-режиме используется seeded brief из `data/demo/investor_v1/morning_briefs_seeded.json` — чтобы на показе не ждать LLM.

## PDF export
Endpoint `/api/ai/morning-brief/{id}/pdf` — генерация через reportlab.
Layout: брендированный (logo, бирюзовый accent) + весь контент брифа + QR-код на веб-версию.

## Deliverables
- `web_cabinet/ai/endpoints/morning_brief.py`
- `web_cabinet/ai/prompts/morning_brief.py` (полный prompt)
- `web_cabinet/ai/background/morning_brief_cron.py`
- `web_cabinet/api/morning_brief_pdf.py`
- Alembic migration: table `morning_briefs`
- `web_app/components/overview/morning-brief-card.tsx`
- `web_app/app/(protected)/dashboard/page.tsx` (интеграция)
- `docs/iterations/MVP-N14_execution_proof.md`

## Acceptance criteria
1. `POST /api/ai/morning-brief` возвращает валидный JSON на русском
2. Cron triggers на тестовом таймере (set CRON_TEST=true → через 1 минуту)
3. /dashboard показывает brief card
4. Demo-mode показывает seeded brief
5. PDF export работает
6. Evidence chips кликабельны → детали
7. Все CI гейты pass

## Формат ответа
Стандартный T34.
