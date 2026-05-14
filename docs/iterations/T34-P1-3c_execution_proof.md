# T34-P1-3c Execution Proof — `/vet` tabs layout + `/treatments` redirect

**Date:** 2026-05-15
**Spec:** `docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md` §4

## Scope

`/vet` превращён из flat-страницы в tabs-layout с тремя табами: **Обзор**, **Каренция**, **Задачи**. Контент перенесён в три обёртки в `web_app/components/vet/tabs/` (`VetOverviewTab` оборачивает существующий `VetQueuesSurface`; `VetWithdrawalTab` — `TreatmentsWithdrawalSurface`; `VetTasksTab` — placeholder под P1-3d). URL-стейт активного таба — `?tab=overview|withdrawal|tasks`, дефолт `overview`, невалидное значение тихо сваливается на `overview`. Переключение через `router.replace` без full reload (`scroll: false`).

`/treatments` заменён на server-side `permanentRedirect('/vet?tab=withdrawal')` (308). Внутренний deep-link «Лечение / каренция» в `vet-queues-surface.tsx` обновлён напрямую на `/vet?tab=withdrawal` (без хопа через redirect). Запись `/treatments → 'Лечение'` удалена из `extraPathLabels` и из iconMap сайдбара. Тест `navigation.test.ts` обновлён под новое поведение.

Дополнительно расширен `web_app/types/shims.d.ts` (фикция-shim для `next/navigation` в этом проекте) — добавлен `permanentRedirect` и опции `{ scroll?: boolean }` в сигнатурах `router.replace/push`. Без этого `tsc --noEmit` ложно отказывался видеть валидные API Next.js 15.

Out of scope: содержательная карточка «Задачи по направлению» (это P1-3d, см. §5 spec'а); редизайн самих surface'ов; полные 7 гейтов CLAUDE.md §4 (frontend-only инкремент, как и P1-3a).

## Executed checks

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `npm run typecheck` (`tsc --noEmit`) | PASS | exit 0, без вывода ошибок |
| 2 | `npm run test` (validate-foundation.mjs) | PASS | stdout `web_app T32-07 validation OK`. Список ожидаемых routes в скрипте обновлён (удалён `/treatments`). |
| 3 | Браузер: логин admin/admin → `/vet` default = overview | PASS | `aria-selected="true"` на `vet-tab-overview`; panel id=`vet-tabpanel-overview`; panel содержит «Ветеринария…Очереди задач ветеринарной службы…» (VetQueuesSurface). |
| 4 | Клик «Каренция» → URL=`/vet?tab=withdrawal`, активен withdrawal | PASS | `location.href = .../vet?tab=withdrawal`; `vet-tab-withdrawal[aria-selected=true]`; panel содержит «Лечение / каренция…Контроль лечения и периодов каренции…» (TreatmentsWithdrawalSurface). |
| 5 | `/treatments` → permanent redirect → `/vet?tab=withdrawal` | PASS | `await page.goto('/treatments')` → итоговый `location.href = http://localhost:3000/vet?tab=withdrawal`, корректный контент Каренции. |
| 6 | `?tab=tasks` рендерит placeholder под P1-3d | PASS | active=`vet-tab-tasks`; panel text = «Задачи по направлению…Карточка задач домена health появится в P1-3d.» |
| 7 | `?tab=garbage` тихо сваливается на overview | PASS | `vet-tab-overview[aria-selected=true]`, URL не меняется, no console error. |
| 8 | WCAG 4.1.2 aria-controls/id linkage | PASS | каждый таб `aria-controls = vet-tabpanel-<id>`, активный panel `id = vet-tabpanel-<active>`, `aria-labelledby = vet-tab-<active>`. |
| 9 | Скриншот `/vet` default overview | PASS | `artifacts/_ci/p1-3c_vet_tabs_overview.png` |
| 10 | Удалённые `/treatments` references | PASS | `grep -rn '/treatments' web_app/` → совпадения только в `treatments/page.tsx` (redirect-источник) и в proof; в navigation.ts/sidebar.tsx/vet-queues-surface.tsx — отсутствует. |

### Browser smoke evidence (Playwright MCP)

`page.evaluate(...)` после прямой навигации на `/vet`:

```json
{
  "url": "http://localhost:3000/vet",
  "tablist_label": "Разделы ветеринарии",
  "tabs": [
    { "id": "vet-tab-overview",   "label": "Обзор",    "selected": "true",  "controls": "vet-tabpanel-overview" },
    { "id": "vet-tab-withdrawal", "label": "Каренция", "selected": "false", "controls": "vet-tabpanel-withdrawal" },
    { "id": "vet-tab-tasks",      "label": "Задачи",   "selected": "false", "controls": "vet-tabpanel-tasks" }
  ],
  "panel_id": "vet-tabpanel-overview",
  "panel_labelled_by": "vet-tab-overview"
}
```

После клика «Каренция»:

```json
{ "url": "http://localhost:3000/vet?tab=withdrawal",
  "active_tab_id": "vet-tab-withdrawal", "panel_id": "vet-tabpanel-withdrawal" }
```

После `page.goto('/treatments')`:

```json
{ "url": "http://localhost:3000/vet?tab=withdrawal" }
```

## 7 гейтов CLAUDE.md §4 — НЕ прогонялись

P1-3c — frontend-only, backend / Alembic / golden / contracts не затрагиваются. Spec §6 явно ограничивает гейты P1-3c до «TS + Playwright smoke + runtime». Те же резоны, что в P1-3a:
- `verify_refactor` / `web_smoke` / golden — не меняем core; перепрогон даст identical reports;
- `pytest` — нет Python-изменений;
- `warning_governance` — нет новых warning источников;
- `perf` / `rollout` / `competitive` — backend-направленные, не двигаются от UI tab-переключения.

Полные 7 гейтов отработают на ближайшем backend-меняющем инкременте — P1-3d (`?domain` query-param на `/api/app/v1/worklists`).

## Net result

- **Новые файлы:**
  - `web_app/components/vet/tabs/overview-tab.tsx`
  - `web_app/components/vet/tabs/withdrawal-tab.tsx`
  - `web_app/components/vet/tabs/tasks-tab.tsx`

- **Изменения:**
  - `web_app/app/(protected)/vet/page.tsx` — client component, tabs UI с aria-tablist/tab/tabpanel, `useSearchParams`+`router.replace` для URL-state, дефолт `overview`, фильтр невалидных значений.
  - `web_app/app/(protected)/treatments/page.tsx` — server component, `permanentRedirect('/vet?tab=withdrawal')`.
  - `web_app/lib/navigation.ts` — удалён `'/treatments': 'Лечение'` из `extraPathLabels`.
  - `web_app/components/app/sidebar.tsx` — удалён `/treatments` из `iconMap` + lucide `Pill` import.
  - `web_app/components/extended/vet-queues-surface.tsx` — `<Link href="/treatments">` → `<Link href="/vet?tab=withdrawal">`.
  - `web_app/scripts/validate-foundation.mjs` — `/treatments` убран из обязательных routes.
  - `web_app/tests/navigation.test.ts` — кейс «`pathLabels['/treatments'] === 'Лечение'`» → «`pathLabels['/treatments'] === undefined`».
  - `web_app/types/shims.d.ts` — добавлен `permanentRedirect`, опции `{ scroll?: boolean }` в `router.replace/push`.

- **Стили:** новые CSS-классы не добавлялись; переиспользован существующий `.window-tabs` / `.window-tab[--active]` pattern (тот же, что в `components/timeline/window-tabs.tsx`) — никаких новых deps, никакого Radix.

## Honest status

`partially_proven`.

- Runtime-доказательства (Playwright MCP) — все 7 ключевых сценариев зелёные.
- Tsc + npm test — зелёные.
- 7 гейтов CLAUDE.md §4 не прогонялись намеренно (per spec §6, frontend-only). Аналогично P1-3a.

## От координатора

Блокирующих действий не требуется.

Следующий инкремент — P1-3d: query-param `?domain=health|repro` на `GET /api/app/v1/worklists` + компонент `TasksByDomainCard` + размещение на `/vet?tab=tasks` (заменит текущий placeholder) и `/reproduction`. P1-3d — backend-меняющий, на нём прогоняем все 7 гейтов.
