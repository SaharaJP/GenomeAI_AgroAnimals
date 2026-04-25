# Дизайн: Перевод пользовательского интерфейса на русский язык

**Дата:** 2026-04-25  
**Подход:** Прямая замена строк (Approach A)  
**Статус:** Approved

## Scope

Заменить все пользовательские английские строки в Next.js-фронтенде на русские. Никаких новых зависимостей, никакой i18n-инфраструктуры — прямая замена в JSX/TS файлах.

## Что меняем

### Навигация
- `web_app/lib/navigation.ts` — метки пунктов меню

### Авторизация
- `web_app/app/login/page.tsx`
- `web_app/components/auth/login-form.tsx`

### Операции
- `web_app/components/operations/alerts-surface.tsx`
- `web_app/components/operations/assistant-interactive-client.tsx`
- `web_app/components/operations/daily-brief-preview.tsx`
- `web_app/components/operations/planner-surface.tsx`
- `web_app/components/operations/daily-operations-dashboard.tsx`
- `web_app/components/operations/worklists-surface.tsx`
- `web_app/components/operations/scope-summary.tsx`
- `web_app/components/operations/alert-list.tsx`

### Аналитика
- `web_app/components/analytics/add-chart-dialog.tsx`
- `web_app/components/analytics/chart-card.tsx`
- `web_app/components/analytics/health-tab.tsx`
- `web_app/components/analytics/production-tab.tsx`
- `web_app/components/analytics/reproduction-tab.tsx`
- `web_app/app/(protected)/analytics/page.tsx`

### Таймлайн
- `web_app/app/(protected)/timeline/page.tsx`

### UI-примитивы
- `web_app/components/ui/filter-bar.tsx`
- `web_app/components/ui/explainability-block.tsx`

### Отчёты
- `web_app/components/reports/report-governance-panel.tsx`

## Что НЕ трогаем

| Файл | Причина |
|------|---------|
| `app/(protected)/design-system/page.tsx` | Технический экран разработчика |
| `app/(protected)/support/page.tsx` | Внутренний/технический |
| `components/extended/parity-evidence-table.tsx` | Технический |
| `components/extended/observability-surface.tsx` | Технический |
| `components/extended/support-governance-surface.tsx` | Технический |
| Весь Python/бэкенд | Вне scope |

## Архитектура изменений

Никаких структурных изменений. Каждая строка `"English text"` заменяется на `"Русский текст"` непосредственно в JSX-разметке или в константах компонента.

## Порядок работы

1. Навигация (`lib/navigation.ts`)
2. Авторизация (`login/page.tsx`, `login-form.tsx`)
3. Операции (все файлы в `components/operations/`)
4. Аналитика (`components/analytics/`, `analytics/page.tsx`)
5. Таймлайн, UI-примитивы, Отчёты

## Acceptance criteria

- `tsc --noEmit` завершается с 0 ошибок после всех изменений
- Все меню, кнопки, заголовки, подписи, плейсхолдеры, сообщения об ошибках на ключевых экранах отображаются на русском
- Нет регрессий в поведении компонентов

## Риски / допущения

- Часть строк уже на русском (например `до {rec.deadline}`) — не трогаем
- Динамические данные из API (имена животных, даты, числа) — не переводим, только UI-лейблы
- Строки в `console.log` и комментариях — не переводим
