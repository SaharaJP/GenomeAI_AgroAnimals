# Задача MVP-N06: Помощник (Copilot) — Briefing UI

**PROMPT:**

## Контекст
- `CLAUDE.md`, `design_decisions.md`
- Скриншот: `docs/design_reference/Снимок экрана 2026-04-21 в 10.00.06.png`
- AI backend: `web_cabinet/ai/endpoints/weekly_brief.py` (из MVP-N17)
- Seeded briefings: `data/demo/investor_v1/seeded_weekly_briefs.json`

## Цель
Страница `/copilot` для генерации еженедельных брифингов фермы через ИИ-помощник.

## Layout (как на скриншоте Connecterra)

### Header
- Breadcrumb "Демо-ферма ▸ Помощник"
- H1: "Помощник: Брифинг фермы"

### Секция 1 — Create Brief
- Card "Используйте Помощника для анализа всех данных вашей фермы"
- Описание: "Выберите начальную и конечную даты, чтобы задать период анализа. Помощник соберёт все недельные тренды, которые происходили в этом периоде. Вы получите брифинг на email, как только он будет готов. Это может занять до 10 минут."
- Date range picker: "Начальная дата → Конечная дата"
- Кнопка "Создать брифинг фермы" (бирюзовая)

### Секция 2 — Settings
- Card "Настройки"
- Toggle: "Включите, чтобы получать email с брифингом фермы каждый понедельник о Демо-ферме"
- Toggle-state бирюзовый когда on

### Секция 3 — Inline preview (новое, не у Connecterra)
После клика "Создать" — inline preview briefing'а:
- Заголовок + дата диапазона
- Narrative 3-4 параграфа
- Ключевые события (bullets)
- Рекомендации с priority badges
- Кнопки: "Отправить на email" / "Скачать PDF"

### Секция 4 — Past briefings (новое)
Collapsible список прошлых briefings с preview.

## Demo mode
Для инвесторского показа — при клике "Создать брифинг" с любыми датами в последних 7 днях → использовать seeded briefing из JSON (<1 секунда response).

В production — real LLM call через `/api/ai/weekly-brief` (до 60 секунд).

## Backend
- `POST /api/ai/weekly-brief` — генерация (из MVP-N17)
- `GET /api/ai/weekly-brief/history` — список прошлых
- `POST /api/ai/weekly-brief/{id}/email` — отправить на email
- `GET /api/ai/weekly-brief/{id}/pdf` — скачать PDF

## Deliverables
- `web_app/app/(protected)/copilot/page.tsx`
- `web_app/components/copilot/create-brief-card.tsx`
- `web_app/components/copilot/brief-preview.tsx`
- `web_app/components/copilot/settings-card.tsx`
- `web_app/components/copilot/past-briefings-list.tsx`
- `web_app/lib/date-range-picker.tsx` (reusable)
- `docs/iterations/MVP-N06_execution_proof.md`

## Acceptance criteria
1. Визуально соответствует Connecterra screenshot
2. Date range picker работает (с русской локалью через date-fns/locale/ru)
3. Клик "Создать" → preview показывается (<1с в demo-mode)
4. Toggle weekly email сохраняется
5. PDF скачивается
6. Все CI гейты pass

## Формат ответа
Стандартный T34.
