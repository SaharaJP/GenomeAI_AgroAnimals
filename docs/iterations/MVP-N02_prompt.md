# Задача MVP-N02: Обзор (Overview) в стиле Connecterra

**PROMPT:**

## Контекст
- `CLAUDE.md`, `design_decisions.md`
- Скриншот-референс: `docs/design_reference/Снимок экрана 2026-04-21 в 09.57.49.png`
- MVP-N01 уже сделан (app shell)

## Цель
Переписать `/dashboard` страницу в Connecterra-style Overview.

## Layout (точно как на скриншоте)

### 1. Info banner сверху
`ℹ Это демо-ферма с тестовыми данными. Она показывает, что приложение делает, как только ваши данные будут подключены.`

### 2. Hero приветствие
- Динамическое по времени суток: "Доброе утро/день/вечер, Андрей!"
- Шрифт Inter, 28-36px, цвет `--text`
- Имя пользователя из auth context

### 3. Attention pill + card
- Pill "⚠ Требует вашего внимания" (светло-бирюзовый фон)
- Ниже карточка:
  - Если есть активные insights → список 2-3 с приоритетом
  - Если нет → empty state "👍 Всё под контролем. Ничего срочного."

### 4. Section heading
`📈 Последние события на вашей ферме`

### 5. 3-колоночная сетка (критичное место!)
Три карточки одинаковой высоты:

**Колонка 1 — Инсайты (💡):**
- Header "Инсайты" + pagination "1 / 5" + стрелки
- Карточка одного insight'а с preview:
  - Название
  - Дата (например "December 31, 2023")
  - Описание 2-3 строки
  - Mini-chart или comparison scale (если применимо)
  - Клик → переход на `/insights/[id]`

**Колонка 2 — Лента событий (🕐):**
- Header "Лента событий"
- Event type dropdown + кнопка "Добавить событие"
- 3-5 последних events, каждый:
  - Иконка типа
  - Название
  - Описание
  - Дата
  - Badge "Результаты готовы"
- Клик → переход на `/timeline`

**Колонка 3 — Данные для изучения (📊):**
- Header "Данные для изучения" + pagination
- Карточка:
  - "Ваша панель"
  - Название метрики (например "DMI per Head for Lactating Cows")
  - Mini-chart (Recharts line, bright green)
- Клик → переход на `/analytics`

### 6. FAB "+"
Из MVP-N01, в правом нижнем. onClick пока toast.

## ИИ-помощник (будет добавлен в MVP-N13)
Пока **не добавляем** chat-widget. В MVP-N02 — только статичный layout.

## Данные
- Из existing `web_cabinet` API endpoints
- Demo данные seeded в MVP-N10 через `data/demo/investor_v1/`

## Ограничения
- Вся копия на русском
- Не ломать навигацию (все клики должны вести на валидные маршруты, даже если там page в работе)
- Empty states — информативные, не "No data"

## Deliverables
- `web_app/app/(protected)/dashboard/page.tsx` — переписан полностью
- `web_app/components/overview/hero-greeting.tsx`
- `web_app/components/overview/attention-card.tsx`
- `web_app/components/overview/insights-column.tsx`
- `web_app/components/overview/timeline-column.tsx`
- `web_app/components/overview/data-column.tsx`
- `web_app/components/overview/info-banner.tsx`
- `docs/iterations/MVP-N02_execution_proof.md`

## Acceptance criteria
1. Визуально **точная копия** Connecterra Overview screenshot
2. 3 карточки равной высоты, консистентное spacing
3. Все клики работают (переходы на другие страницы — корректные)
4. Русский копирайтинг везде
5. Responsive: на `< 768px` — колонки в стек
6. `npm run typecheck` + `npm run build` pass
7. Все 7 CI гейтов pass

## Формат ответа
Scope → План → Deliverables → Acceptance → Проверки → Риски → От координатора.
Статус: proven / partially_proven / not_proven / blocked.
