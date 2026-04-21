# Задача MVP-N17: Weekly Brief Full Generator

**PROMPT:**

## Контекст
- AI-gateway: MVP-N11
- Farm context + tools: MVP-N12
- Morning brief (похожая логика): MVP-N14
- Copilot UI: MVP-N06

## Цель
Полноценный weekly farm briefing — это главная Copilot-фича у Connecterra. AI генерит развёрнутый отчёт за диапазон дат с трендами, аномалиями, 5+ рекомендациями.

## Backend

### POST /api/ai/weekly-brief

Request:
```json
{
  "farm_id": "demo-farm-v1",
  "start_date": "2026-04-14",
  "end_date": "2026-04-21",
  "language": "ru",
  "deliver_email": false
}
```

Response (Pydantic WeeklyBrief):
```python
class WeeklyBrief(BaseModel):
    brief_id: str
    farm_id: str
    period: DateRange
    generated_at_utc: datetime
    
    title: str  # "Недельный отчёт: 14-21 апреля 2026"
    executive_summary: str  # 2-3 предложения
    
    sections: list[BriefSection]
    
    key_recommendations: list[KeyRecommendation]  # 3-7 priorities
    anomalies_detected: list[Anomaly]
    
    kpi_table: dict  # структурированная таблица KPI с дельтами
    
    generation_model: str
    generation_tokens: dict

class BriefSection(BaseModel):
    heading: str  # "Продуктивность", "Воспроизводство", "Здоровье", "Кормление"
    narrative: str  # 2-4 параграфа
    highlights: list[str]  # ключевые моменты
    evidence_ids: list[str]

class KeyRecommendation(BaseModel):
    recommendation: str
    priority: Literal["high", "medium", "low"]
    rationale: str  # почему важно
    expected_outcome: str  # ожидаемый результат
    affected_entities: list[str]  # cow_ids, group_ids

class Anomaly(BaseModel):
    description: str
    severity: Literal["critical", "warning", "info"]
    evidence_id: str
```

### Логика
1. Load farm_context за весь период (period_days = days между start и end)
2. Aggregate KPI с трендами
3. Поиск аномалий (>2σ отклонения)
4. Load all events в период
5. Claude **Opus 4.7** (качество > скорости)
6. System prompt: WEEKLY_BRIEF_SYSTEM
7. Tool use разрешено — AI может копаться в деталях
8. Structured output (Pydantic)
9. Validate all evidence_ids
10. Save в БД
11. Optional: email delivery через SMTP

### WEEKLY_BRIEF_SYSTEM prompt
(полный, русский)

Ключевые требования:
- Структура: Summary → Sections (по областям) → Key Recommendations → Anomalies
- Длина: ~800-1500 слов total
- Тон: профессиональный executive briefing
- Секции обязательные: Продуктивность, Воспроизводство, Здоровье, Кормление (если есть данные)
- 3-7 top recommendations с priority
- Evidence для каждого утверждения
- Без marketing bullshit

## Email delivery
Если `deliver_email=true`:
- Render WeeklyBrief → HTML через Jinja2 template
- SMTP send через existing web_cabinet/mailer (если есть) или stub

## PDF export

GET /api/ai/weekly-brief/{id}/pdf:
- reportlab template: logo, бирюзовый accent, структура секций
- Красиво отформатирован для печати/отправки инвесторам/клиентам

## Intergation с UI (MVP-N06)

### В /copilot page
- Клик "Создать брифинг фермы" → POST /api/ai/weekly-brief
- Loading state: "ИИ-помощник анализирует данные вашей фермы... ~60 секунд"
- При готовности → inline preview
- Inline preview показывает все секции collapsible
- Кнопки: [📄 Скачать PDF] [📧 Отправить на email] [🔄 Перегенерировать]

### Weekly cron (если toggle "каждый понедельник" включён)
Cron каждый понедельник 07:00 MSK → генерит brief за прошлую неделю → email.

## Demo mode
Seeded weekly briefings в `data/demo/investor_v1/weekly_briefs_seeded.json` для 3 диапазонов дат.

При GENOMEAI_AI_DEMO_MODE=true и если запрашиваемый period matches seeded → instant response.

## Deliverables
- `web_cabinet/ai/endpoints/weekly_brief.py`
- `web_cabinet/ai/prompts/weekly_brief.py` (полный prompt)
- `web_cabinet/ai/background/weekly_brief_cron.py`
- `web_cabinet/templates/email/weekly_brief.html.j2` (email template)
- `web_cabinet/api/weekly_brief_pdf.py`
- Alembic migration: table `weekly_briefs`
- Обновление `web_app/app/(protected)/copilot/page.tsx` — подключить real API
- Tests: test_weekly_brief.py
- `docs/iterations/MVP-N17_execution_proof.md`

## Acceptance criteria
1. POST /api/ai/weekly-brief возвращает WeeklyBrief валидный
2. Narrative на русском, качественный, с evidence
3. Минимум 3 sections сгенерированы
4. 3-7 recommendations с rationale
5. PDF export корректный
6. Demo-mode работает instantly
7. Все CI гейты pass

## Формат ответа
Стандартный T34.
