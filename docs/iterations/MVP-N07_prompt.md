# Задача MVP-N07: Add Event FAB (круглая кнопка "+")

**PROMPT:**

## Контекст
- FAB placeholder создан в MVP-N01
- Теперь делаем реальный flow добавления события

## Цель
FAB "+" в правом нижнем углу на всех protected pages → при клике открывается dialog/drawer для быстрого добавления событий на ферме.

## UI

### FAB
- Круглая 56px (на desktop), 48px на mobile
- Бирюзовая `#2dd4bf`
- При клике — пульсирует один раз (scale 1→1.1→1)
- Открывает Dialog (desktop) или Drawer snap-to-top (mobile)

### Dialog содержимое
Header: "Добавить событие"

Поля:
1. **Тип события** (Select с иконкой):
   - 🌾 Смена рациона
   - 🏡 Перевод группы
   - 👤 Новый сотрудник
   - 🍽 График кормления
   - 🦶 Обработка копыт
   - 💉 Вакцинация
   - 🧹 Смена подстилки
   - 📐 Изменение плотности
   - 🔬 Лабораторные тесты
   - 📋 Другое (custom text)

2. **Дата** (date picker):
   - По умолчанию — сегодня
   - Локаль русская

3. **Заголовок** (short input):
   - Placeholder в зависимости от типа
   - Например для "Смена рациона": "Добавление новой добавки в рацион"

4. **Описание** (textarea):
   - Placeholder: "Опишите детали изменения..."

5. **Затронутые группы** (multi-select):
   - Список групп фермы из БД
   - Варианты: "Все коровы", "Дойные", "Close-up", "Fresh cows", "Группа 1-5"

6. **Прикрепить файл** (опционально, в MVP — stub):
   - "Прикрепить файл (например PDF с лабораторными)"

Кнопки:
- "Отмена" (outline)
- "Добавить" (бирюзовая)

### После submit
- Валидация: все обязательные поля
- API call: `POST /api/timeline/events`
- Toast success: "Событие добавлено в Ленту. Результаты будут готовы через ~24ч."
- Dialog закрывается
- Событие немедленно появляется в Ленте событий (на `/timeline`)
- Если у пользователя открыта страница `/timeline` в другой вкладке — SSE push обновления

## Интеграция
- Клик FAB на `/dashboard` → open dialog
- Клик FAB на `/insights` → open dialog  
- Клик FAB на `/analytics` → open dialog
- Клик FAB на `/timeline` → open dialog (там ещё и кнопка "+ Добавить событие" — обе работают одинаково)
- Клик FAB на `/copilot` → open dialog

## Backend
- `POST /api/timeline/events` — add event
  - Request: `{type, date, title, description, affected_groups, attachments}`
  - Response: `{event_id, status: "pending_analysis"}`
- Event сохраняется в БД, flag `pending_analysis: true`
- Cron задача (ai insight scanner из MVP-N15) через N часов генерит impact analysis

## Deliverables
- `web_app/components/app/add-event-dialog.tsx`
- `web_app/components/app/fab.tsx` — обновить onClick → openDialog
- `web_app/components/app/event-type-select.tsx`
- `web_cabinet/api/timeline/add_event.py`
- Alembic migration (если нужно новое поле `pending_analysis`)
- `docs/iterations/MVP-N07_execution_proof.md`

## Acceptance criteria
1. FAB видим на 5 protected страницах
2. Клик открывает dialog корректно
3. Все типы событий доступны, иконки правильные
4. Сохранение в БД работает, event появляется в /timeline
5. Mobile: drawer slides up from bottom
6. Все CI гейты pass

## Формат ответа
Стандартный T34.
