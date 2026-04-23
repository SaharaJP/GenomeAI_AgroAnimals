# Задача MVP-N04: Аналитика (BI dashboard)

**PROMPT:**

## Контекст
- `CLAUDE.md`, `design_decisions.md`
- Скриншоты: `docs/design_reference/Снимок экрана 2026-04-21 в 09.58.30.png`, `.58.59.png`, `.59.17.png`, `.59.27.png`, `.59.42.png`
- Endpoints /api/analytics/* готовятся в параллельной задаче MVP-N04-data

## Цель
BI-страница с табами (Продуктивность / Воспроизводство / Здоровье) и кастомизируемыми графиками.

## Layout

### Верхняя часть
- Subtitle: "Визуализируйте данные вашей фермы для выявления трендов и возможностей"
- Таб-панель: **Продуктивность** / **Корм** / **Воспроизводство** / **Здоровье** / **Поведение** / **Состав стада** / **Погода** / **Финансы** / **+**
  - Крестик на каждом табе для удаления
  - "+" для добавления нового
- Правый верх: "Сравнить графики" / "Переименовать панель" / "Копировать панель" / "+ Добавить график"

### В MVP реализуем только 3 таба:
1. **Продуктивность** (default open)
2. **Воспроизводство**
3. **Здоровье**

Остальные — visible в UI, но при клике — empty state "Скоро".

### Структура таба
2x2 grid графиков. Каждая карточка:
- Title + info icon
- Badges ниже: `📊 Per farm` / `📈 Milking system, Shipped milk`
- Chart (Recharts LineChart или StackedBarChart для Health)
- Tooltip на hover с точным значением + датой
- Правый верх карточки: `▵` (alert) / `⌫` (delete) / `✎` (rename)

### Графики в табе Продуктивность
1. **Milk yield and ECM** — 2 линии (milk yield, ECM yield), даты X
2. **Fat & protein %** — 2 линии
3. **Somatic Cell Count (SCC)** — 1 линия (красный если > 200k)
4. **Слот "+ Добавить график"** — empty state с pictogram и ссылкой

### Графики в табе Воспроизводство
1. **Reproduction rates** — 3 линии: Conception / Pregnancy / Insemination rate
2. **Days open after calving** — multi-line (по лактациям 1-7)
3. **Calculated VWP** — all lactating cows, 2 линии (Lactation 1, 2+)
4. **Calculated VWP and avg age at first breeding — youngstock**

### Графики в табе Здоровье
1. **Cows with mastitis (#)** — line chart
2. **Cows with health issues (#)** — stacked bar (diarrhea, ketosis, lameness, mastitis, metritis, milk fever, pneumonia, retained placenta, other)
3. Два пустых слота "+ Добавить график"

## Добавление графика
При клике "+ Добавить график":
- Открывается modal/drawer с search
- Grid карточек с preview метрик
- Группировка: Production / Feed / Reproduction / Health / ...
- Клик на карточку → график добавляется в текущий dashboard
- Drag-n-drop для reorder (если времени хватит)

## Backend
Endpoints (создаются в MVP-N04-data):
- `/api/analytics/production?start=...&end=...`
- `/api/analytics/reproduction?...`
- `/api/analytics/health?...`

## Deliverables
- `web_app/app/(protected)/analytics/page.tsx`
- `web_app/components/analytics/analytics-tabs.tsx`
- `web_app/components/analytics/chart-card.tsx`
- `web_app/components/analytics/production-tab.tsx`
- `web_app/components/analytics/reproduction-tab.tsx`
- `web_app/components/analytics/health-tab.tsx`
- `web_app/components/analytics/add-chart-dialog.tsx`
- `web_app/components/analytics/empty-chart-slot.tsx`
- `docs/iterations/MVP-N04_execution_proof.md`

## Acceptance criteria
1. 3 таба работают, визуально соответствуют Connecterra screenshot
2. Графики отображаются с реальными seeded data за 6 месяцев
3. Tooltip корректно показывает значения
4. Можно добавить график через dialog (даже если сохранение в БД — stub)
5. Все CI гейты pass

## Формат ответа
Стандартный T34.
