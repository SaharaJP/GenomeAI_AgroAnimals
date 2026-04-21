# Задача MVP-N05: Лента событий + Impact Analysis ★ KILLER-ФИЧА

**PROMPT:**

## Контекст
- `CLAUDE.md`, `design_decisions.md`
- **Главный референс**: `docs/design_reference/Снимок экрана 2026-04-21 в 09.59.53.png`
  — внимательно изучи перед началом работы
- Seeded events: `data/demo/investor_v1/seeded_timeline_events.json`
- Seeded impact: `data/demo/investor_v1/seeded_impact_analyses.json`

## Цель
Реализовать Farm Timeline с Impact Analysis — **главную wow-фичу демо** (Акт 4).
Это то, что отличает GenomeAI от всех конкурентов: возможность видеть влияние КАЖДОГО решения.

## Layout (два колонка)

### Левая колонка (~40% ширины): Chronological list
- Подзаголовок страницы: "Хроника событий на ферме в хронологическом порядке, с оценкой их влияния."
- Event type dropdown + кнопка **"+ Добавить событие"** (бирюзовая)
- Список events группированных по месяцам:
  - "Мар 2026" (header)
    - Event card 1
    - Event card 2
  - "Фев 2026"
    - ...
  - "Янв 2026"
    - ...

**Event card:**
- Иконка типа события (Lucide)
- Название (например "Смена рациона — добавлено Ezfeed")
- Описание 1-2 строки
- Дата (например "11 марта 2026")
- Badge справа "Результаты готовы" (зелёная галочка)
- Клик → выбирается (бирюзовая обводка) + справа появляется impact

### Правая колонка (~60% ширины): Impact panel
Появляется при выборе события.

**Верх:**
- Иконка типа + название event
- Дата + "a month ago"
- Подпись "Automatically added by your feed software" (source)

**Потенциально затронутые метрики (badge "Beta"):**
- Текст пояснение: "Оцените KPI ДО и ПОСЛЕ изменения, чтобы понять его влияние. Используйте переключатель projections, чтобы увидеть значения ключевых метрик, если бы изменение не произошло (если доступно)."

**Диапазоны ДО / ПОСЛЕ:**
- "До: 08.03.2026 — 11.03.2026"
- "После: 11.03.2026 — 14.03.2026"
- Табы переключения: **3 дня** / **1 неделя** / **2 недели** / **4 недели**

**Метрические карточки (grid 2x2 или 2x3):**
Каждая карточка показывает одну метрику:
- Название: например "DMI per group"
- "До: 19.5 кг" + фон-бар (light bluish)
- "После: 18.4 кг" + фон-бар (dark teal)
- Справа: стрелка ↓ + дельта "1.1 кг" в красной подсветке (для падения), зелёной для роста, серой для no change

Примеры метрик:
- DMI per group
- Время поедания в день, per pen
- ECM yield per cow per pen
- Average Milk Yield per cow, per pen (milking system)
- Время руминации per pen, per day

**Кнопка "Добавить ещё график":**
Select dropdown с метриками + кнопка "+ Add"

**Секция "Что ещё случилось?":**
Подзаголовок: "Другие изменения в метриках, которые могут быть связаны с этим событием"
Таблица:
| метрика | До | После | Изменение |
|---|---|---|---|
| THI | 48 | 50 | ↑ 2 (Рост) |

## Seeded events для демо (8-12)
1. "Смена рациона — добавлено Ezfeed" (11 мар) — основной для демо
2. "Новый сотрудник на доильном зале" (6 мар)
3. "График кормления — Dry Cows pen" (25 фев)
4. "Смена рациона для пенна 7" (19 фев)
5. "Возврат к кукурузе высокой влажности" (15 фев)
6. "Обрезка копыт — пенн hooftrim total pen" (7 фев)
7. "Плотность в Close-up пенне" (25 янв)
8. "Новая подстилка для группы 3" (17 янв)

## AI-интеграция
- Narrative описание impact может быть сгенерировано через `/api/ai/impact-narrative` (MVP-N16)
- В demo-режиме — используется seeded data
- В production-режиме — вызывается AI endpoint

## Backend
- `GET /api/timeline/events?start=...&end=...` — список events
- `GET /api/timeline/events/[id]/impact?window=7d` — impact data
- `POST /api/timeline/events` — add event (связь с MVP-N07)

## Deliverables
- `web_app/app/(protected)/timeline/page.tsx`
- `web_app/components/timeline/event-list.tsx`
- `web_app/components/timeline/event-card.tsx`
- `web_app/components/timeline/impact-panel.tsx`
- `web_app/components/timeline/metric-compare-card.tsx` (До/После визуализация)
- `web_app/components/timeline/other-changes-table.tsx`
- `web_app/components/timeline/window-tabs.tsx` (3дн/1нед/2нед/4нед)
- `web_cabinet/api/timeline/` endpoints
- `docs/iterations/MVP-N05_execution_proof.md`

## Acceptance criteria
1. Визуально точно соответствует Connecterra Farm Timeline screenshot
2. 8+ seeded events видны в list
3. Клик на event → impact panel загружается
4. Переключение window (3d/1w/2w/4w) обновляет данные
5. Минимум 4 метрики показывают valid before/after
6. "Что ещё случилось" показывает 2-5 связанных изменений
7. Визуально эффектно — wow при показе
8. Все CI гейты pass

## Риски
- Самая большая задача. Заложи 3 дня.
- Если не укладываешься — минимум: left list + impact panel для 1 window (3d) с 4 метриками. Остальное — polish.

## Формат ответа
Стандартный T34.
