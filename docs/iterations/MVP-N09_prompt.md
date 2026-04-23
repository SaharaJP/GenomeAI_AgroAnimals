# Задача MVP-N09: Settings + Connections

**PROMPT:**

## Контекст
- Скриншоты:
  - Settings: `docs/design_reference/Снимок экрана 2026-04-21 в 10.00.58.png`
  - Connections: `docs/design_reference/Снимок экрана 2026-04-21 в 10.00.46.png`

## Цель
Реализовать страницы /settings и /connections в Connecterra-style.

## Страница `/settings`

### Табы
- **Общее** (default open)
- **Входные данные фермы**

### Таб "Общее"

#### Account details
- "Имя": Андрей Жиров (из auth)
- "Email": icreem714@gmail.com
- "Language and units": 🇷🇺 Русский — кг/°C (dropdown, пока fixed)

#### Notifications
Header: "Уведомления"
Subtitle: "Выберите, какие уведомления вы хотите получать"

Table rows:
- Feature: "KPI Инсайты" (tooltip icon)
  - Right: toggle "email" (on/off)

#### Weekly Farm briefings (Powered by Copilot)
- Card "Еженедельные брифинги фермы от ИИ-помощника"
- Description: "Включите, чтобы получать email с брифингом фермы каждый понедельник о Демо-ферме"
- Toggle on/off

#### Integrated data sources
Header: "Подключённые источники данных"
Subtitle: "Данные реального времени из внешних систем, подключённых к нашей платформе. Легко отслеживайте последние импорты, чтобы инсайты всегда были актуальны."

Table:
| Система | Тип данных | Последнее обновление |
|---|---|---|
| BoviSync | Данные коров, Доильная система, Тест молока | Суббота, 21 марта 2026, 01:02 |
| Datamars Livestock Active Tag | Поведение | Суббота, 21 марта 2026, 12:04 |
| DFA | Вывоз молока | Суббота, 21 марта 2026, 13:00 |

Эти системы — mock, для демонстрации архитектуры.

### Таб "Входные данные фермы"
- Placeholder "Скоро" с pictogram

## Страница `/connections`

### Layout
Header: "Подключённые фермы"
Subtitle: "Фермы, к которым у вас есть доступ"
Right button: "+ Подключить новую ферму" (outline-teal)

### Таб "Farms"
Table:
| Название фермы | Статус |
|---|---|
| Демо-ферма | Sandbox |

При клике "+ Подключить новую ферму" → toast "Функция в разработке. Свяжитесь с саппортом чтобы подключить ферму."

## Backend
- `GET /api/user/settings` — текущие настройки
- `POST /api/user/settings` — обновить
- `GET /api/connections` — список подключённых ферм (mock)
- `GET /api/integrations` — список data sources (mock)

## Deliverables
- `web_app/app/(protected)/settings/page.tsx`
- `web_app/app/(protected)/connections/page.tsx`
- `web_app/components/settings/settings-tabs.tsx`
- `web_app/components/settings/account-details.tsx`
- `web_app/components/settings/notifications-table.tsx`
- `web_app/components/settings/integrations-table.tsx`
- `web_app/components/connections/farms-list.tsx`
- `docs/iterations/MVP-N09_execution_proof.md`

## Acceptance criteria
1. Обе страницы соответствуют Connecterra скриншотам
2. Toggles сохраняют состояние (в localStorage или backend)
3. Mock data для integrations показывается правильно
4. "Sign out" из sidebar работает
5. Все CI гейты pass

## Формат ответа
Стандартный T34.
