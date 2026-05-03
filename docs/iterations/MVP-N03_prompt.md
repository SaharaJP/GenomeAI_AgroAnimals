# Задача MVP-N03: Инсайты (triage + drill-down)

**PROMPT:**

## Контекст
- `CLAUDE.md`, `design_decisions.md`
- Скриншот: `docs/design_reference/Снимок экрана 2026-04-21 в 09.58.09.png` (triage list)
- Seeded data: `data/demo/investor_v1/seeded_insights.json` (12 insights, из MVP-N10-b)

## Цель
Реализовать Connecterra-style Insights triage system с drill-down страницей.

## 1. Страница `/insights` (triage list)

### Layout
- Кнопка "Настройка инсайтов" справа сверху (placeholder onclick → toast)
- Табы: **К проверке (5)** / **В работе** / **Закрыто** — с красным кружком-числом на активном
- Таблица:
  | Инсайт | Ферма | Период | ➜ |
  |---|---|---|---|
  | 💡 Название инсайта | Badge "Демо-ферма" | Дата | chevron-right |
- Красная точка (●) слева от названия для unread/new
- Клик на строку → `/insights/[id]`
- Pagination внизу (если >10)

### Seeded insights (из MVP-N10-b)
Примеры заголовков на русском:
1. "Максимальный THI и затраты на корм"
2. "Максимальный THI и жирность %"
3. "Максимальный THI и количество соматических клеток"
4. "Максимальный THI и DMI для дойных коров"
5. "Максимальный THI и белок %"
6. "Падение удоя в группе 3 после смены рациона"
7. "Увеличение открытых дней в 3+ лактации"
8. "Рост случаев мастита после смены подстилки"
9. "Высокая плотность в close-up группе"
10. "Эффективность корма снижается 14 дней подряд"
11. "Удой Звёздочки (4821) упал на 22% за 9 дней" ← клик ведёт к evidence
12. "3 коровы пропустили последние проверки стельности"

## 2. Страница `/insights/[id]` (drill-down)

### Layout
- Breadcrumb "Инсайты ▸ Название"
- H1: Название инсайта
- Badge priority + дата
- Основной контент:

**Описание (narrative):**
Конкретными числами, например:
"В декабре 2025 при THI=65 стоимость корма на корову была $5.92. При THI=75 этот показатель упал до $5.51 — снижение на 6.85%. Дальнейший рост THI выше 72 коррелирует с уменьшением поедаемости корма на 3-5%."

**Основной график:**
Recharts line chart с tooltip, показывает динамику главной метрики.

**Comparison scale (горизонтальная):**
Visual bar с градиентом красный → зелёный, маркер "где ваша ферма"
Caption: "Сравнение с другими фермами: фермы с высоким impact слева, с низким — справа"

**Recommended actions:**
Numbered list с checkboxes, например:
- [ ] Проверить систему вентиляции в группе 3 (до 15 мая)
- [ ] Скорректировать рацион — увеличить концентрат на 5% в hot days
- [ ] Мониторить DMI ежедневно в течение следующих 14 дней

**Actions:**
- "Пометить как В работе" (primary бирюзовая)
- "Закрыть" (outline)
- "Назад к списку"

### AI-интеграция (связь с MVP-N11/N12)
- Description и recommendations:
  - В demo-режиме: берутся из seeded JSON
  - В production: через endpoint `/api/ai/insight-narrative`
- Главный график: real data из Postgres

## 3. Backend endpoints

- `GET /api/insights?status=to_check|to_follow_up|done` — список
- `GET /api/insights/[id]` — detail (с narrative из AI кэша)
- `POST /api/insights/[id]/transition` — изменить статус
- `POST /api/insights/generate` — триггерит insight scanner (для тестирования)

## Deliverables
- `web_app/app/(protected)/insights/page.tsx` — triage
- `web_app/app/(protected)/insights/[id]/page.tsx` — detail
- `web_app/components/insights/insight-card.tsx`
- `web_app/components/insights/triage-tabs.tsx`
- `web_app/components/insights/comparison-scale.tsx`
- `web_app/components/insights/action-checklist.tsx`
- `web_app/components/insights/insight-chart.tsx`
- `web_cabinet/api/insights/` — endpoints
- Миграция: таблица `insights` с полем `status` (to_check/to_follow_up/done)
- Scripts: seed 12 insights в БД
- `docs/iterations/MVP-N03_execution_proof.md`

## Acceptance criteria
1. 12 seeded insights видны в triage list
2. Табы показывают correct counts
3. Клик на инсайт → detail с графиком + description + recommendations
4. Транзиции статусов работают
5. Визуально соответствует Connecterra
6. Все CI гейты pass

## Формат ответа
Стандартный T34.
