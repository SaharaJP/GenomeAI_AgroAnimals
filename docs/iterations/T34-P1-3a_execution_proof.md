# T34-P1-3a Execution Proof — Navigation accordion 'Стадо'

**Date:** 2026-05-15
**Spec:** `docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md` §2
**Plan:** `docs/superpowers/plans/2026-05-15-p1-3a-navigation-accordion.md`

## Commits

1. `35bdbc0` feat(web): useNavGroupsOpen hook for sidebar accordion state (P1-3a)
2. `f697a9f` feat(nav): accordion 'Стадо' group with discriminated NavigationItem union (P1-3a)
3. `00ece99` fix(nav): post-review polish for P1-3a accordion

## Scope

`NavigationItem` плоский тип заменён на discriminated union `NavigationLeaf | NavigationGroup` ровно с одним уровнем вложенности. Воспроизводство и Ветеринария переехали из секции «Управление» под новую группу-аккордеон «Стадо» в секции «Основное»; добавлен ребёнок `/feeding` (страница появится в P1-3b). Sidebar рендерит группу как collapsible toggle с chevron'ом и nested children; open-state хранится в `localStorage['nav.groups.open']`; pathname текущей страницы форсит auto-expand активной группы. WCAG 4.1.2 linkage — `aria-controls` ↔ `id`. `pathLabels` рекурсивно собирается из обоих уровней.

`/feeding` — leaf в навигации, но страница сама не существует до P1-3b. Промежуточный 404 на клик по «Кормление» — приемлемое состояние между двумя инкрементами одного эпика.

## Executed checks

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `npm run typecheck` (tsc --noEmit) | PASS (exit 0) | `cd web_app && npm run typecheck` — без вывода ошибок |
| 2 | `npm run test` (validate-foundation.mjs) | PASS | stdout: `web_app T32-07 validation OK` |
| 3 | Браузер-логин admin/admin → /dashboard | PASS | Playwright MCP, snapshot захвачен |
| 4 | Sidebar: «Стадо» рендерится как button с chevron в expanded mode | PASS | accessibility tree показывает `button [expanded] [active]` с двумя img (icon + chevron) |
| 5 | Click «Стадо» → раскрывается группа с 4 детьми | PASS | accessibility tree: `group "Стадо"` с 4 link'ами: /profiles/animal, /reproduction, /vet, /feeding |
| 6 | Auto-expand при прямой навигации `/reproduction` | PASS | без явного toggle: `button [expanded]`, группа открыта |
| 7 | WCAG 4.1.2 aria-controls/id linkage | PASS | `aria_controls === children_id` (`nav-group-%D0%A1%D1%82%D0%B0%D0%B4%D0%BE`) |
| 8 | localStorage persistence | PASS | `localStorage['nav.groups.open'] = ["Стадо"]` после toggle |
| 9 | «Управление» больше не содержит Repro/Vet | PASS | accessibility tree «Управление» = только Задачи/Решения/Экономика |
| 10 | Скриншот сайдбара (auto-expanded на /reproduction) | PASS | `artifacts/_ci/p1-3a_accordion_reproduction.png` (gitignored) |

### Browser smoke evidence (Playwright MCP)

DOM-проверка через `page.evaluate(...)` после auto-expand на `/reproduction`:

```json
{
  "aria_expanded": "true",
  "aria_controls": "nav-group-%D0%A1%D1%82%D0%B0%D0%B4%D0%BE",
  "children_id":   "nav-group-%D0%A1%D1%82%D0%B0%D0%B4%D0%BE",
  "linkage_ok": true,
  "localStorage_nav_groups_open": "[\"Стадо\"]"
}
```

Структура `nav[aria-label="Основная навигация"]` после auto-expand:

```
Основное:
  /dashboard, /daily-summary, /insights, /analytics, /timeline
  button "Стадо" [expanded]
    group "Стадо":
      /profiles/animal
      /reproduction
      /vet
      /feeding
Управление:
  /worklists, /decisions, /economics    ← Repro/Vet ушли в Стадо ✓
Сервисы:
  /readiness, /observability, /admin
```

## Code review history

Code-review subagent на commit `f697a9f` нашёл два Important issue:
1. **autoOpenLabels identity churn** — useCallback dep был массивом, isOpen ref пересоздавался каждый render
2. **Missing aria-controls/id linkage** — WCAG 4.1.2

Оба исправлены в `00ece99`. Re-review — APPROVED. Третья Nit-нота (pathLabels['/profiles/animal'] = 'Животные' вместо 'Стадо') — намеренное поведение per spec §2.3 (leaf-label побеждает над group-label в pathLabels).

## 7 гейтов CLAUDE.md §4 — НЕ прогонялись

P1-3a — frontend-only, backend / golden / migrations не затрагиваются. Прогонять `bash scripts/run_ci_gate.sh`, `genomeai verify_refactor`, и т.д. на этом инкременте — бесполезно. Полные 7 гейтов отрабатываются на ближайшем backend-инкременте P1-3b (`/feeding/rations` + `/feeding/intake-drops` endpoint'ы — туда же golden/perf/competitive).

## Net result

- `web_app/lib/hooks/use-nav-groups-open.ts` — новый client-side хук, SSR-safe, localStorage persistence, stable callback identity (depends on joined key, не array ref).
- `web_app/lib/navigation.ts` — discriminated union, recursive pathLabels, group-aware permission filter.
- `web_app/tests/navigation.test.ts` — 9 кейсов (4 существующих + 5 новых); compile-checked через `tsc --noEmit`, не исполняются в текущем CI (нет TS runner — vitest/tsx).
- `web_app/components/app/sidebar.tsx` — `renderGroup`/`renderLeaf` helpers, Wheat-иконка для /feeding, корректный bottomHrefs-фильтр для union-типа, aria-controls/id linkage.
- `web_app/app/globals.css` — 5 новых классов `.nav-group*` / `.nav-link-nested`.

## Honest status

`partially_proven`.

- Frontend изменения **runtime-доказаны** браузерным smoke'ом (Playwright MCP: открытие/закрытие, auto-expand, persistence, aria-linkage).
- 7 гейтов CLAUDE.md §4 **не прогонялись** (frontend-only; backend/golden/perf не затронуты). Они отработают на ближайшем инкременте, трогающем backend — P1-3b.
- Тесты `navigation.test.ts` — **compile-checked** (`tsc --noEmit` exit 0), но не исполняются автоматически в CI (отсутствует TS-runner). Это известный долг репозитория — не пытаемся починить в этом инкременте.

## От координатора

Блокирующих действий не требуется. Следующий инкремент P1-3b (новые endpoint'ы `/feeding/rations` и `/feeding/intake-drops` + страница `/feeding`) — backend-меняющий, потребует 7 гейтов и решение по `feed_intake_drop` insight-`kind` (см. spec §3.2 / §7 п.1).
