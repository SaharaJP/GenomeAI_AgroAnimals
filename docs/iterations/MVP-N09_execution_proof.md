# MVP-N09 Execution Proof — Settings + Connections

## Scope

Реализованы страницы `/settings` и `/connections` в Connecterra-style.
Добавлен UI-компонент Toggle, три mock API-маршрута, компоненты настроек и подключений.
Обновлены ссылки в sidebar и labels в topbar.

## Delivered files

| File | Purpose |
|------|---------|
| `web_app/app/api/user/settings/route.ts` | GET/POST mock settings store |
| `web_app/app/api/connections/route.ts` | GET mock farms list |
| `web_app/app/api/integrations/route.ts` | GET mock data sources |
| `web_app/app/(protected)/settings/page.tsx` | Settings page shell |
| `web_app/app/(protected)/connections/page.tsx` | Connections page shell |
| `web_app/components/ui/toggle.tsx` | Reusable iOS-style toggle switch |
| `web_app/components/settings/settings-tabs.tsx` | Tab logic + settings state management |
| `web_app/components/settings/account-details.tsx` | Account details display card |
| `web_app/components/settings/notifications-table.tsx` | Notifications table + weekly briefing card |
| `web_app/components/settings/integrations-table.tsx` | Integrated data sources table |
| `web_app/components/connections/farms-list.tsx` | Farms list with toast on connect |
| `web_app/app/globals.css` | Added: toggle, settings, connections CSS |
| `web_app/components/app/sidebar.tsx` | Updated hrefs: /connections, /settings |
| `web_app/components/app/topbar.tsx` | Added path labels for /settings, /connections |

## Executed checks

- TypeScript: компоненты не используют запрещённых конструкций; impорты корректны.
- CSS: toggle-track/toggle-thumb классы определены; settings-*/connections-* классы определены.
- Sidebar: `href="/connections"` и `href="/settings"` заменили `/readiness` и `/admin`.
- Topbar: добавлены `'/settings': 'Настройки'` и `'/connections': 'Мои подключения'`.
- API-маршруты возвращают JSON без внешних зависимостей (pure mock).
- Toast при клике "+ Подключить новую ферму" — отображается 4 сек.
- Toggle: optimistic update + POST `/api/user/settings`.

## Net result

- `/settings` — страница с двумя табами, account details, toggles, integrations table.
- `/connections` — страница с farms table и toast при попытке подключить ферму.
- Sidebar "Мои подключения" → `/connections`, "Настройки" → `/settings`.
- Topbar breadcrumb отображает корректные labels.

## Honest status

`not_proven` — runtime-прогон на живом контуре не выполнен; CI gates не запускались.
UI-логика покрыта кодом, соответствует дизайн-референсу, TypeScript-импорты проверены статически.
