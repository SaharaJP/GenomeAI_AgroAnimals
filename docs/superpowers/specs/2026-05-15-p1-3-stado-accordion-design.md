# P1-3 «Стадо» — Accordion-навигация, /feeding, таб Каренция, секции «Задачи по направлению»

**Дата:** 2026-05-15
**Источник:** `docs/iterations/T34-product-backlog-2026-05.md` §P1-3
**Брейншторм-протокол:** в conversation от 2026-05-14/15 (см. memory: P1-3a/b/c/d увязка)
**Статус:** approved (architecture & details), pending implementation plan

---

## 1. Цель и scope

Превратить пункт «Стадо» в сайдбаре из плоской ссылки на `/profiles/animal` в **группу-аккордеон** с подпунктами Животные / Воспроизводство / Ветеринария / Кормление. Параллельно:

- ввести минимальный каркас новой страницы `/feeding` (рационы по группам + группы со снижением потребления корма);
- вложить `/treatments` как таб «Каренция» внутри `/vet`, оставив старый URL рабочим через 308-redirect;
- добавить на `/vet` и `/reproduction` summary-card «Задачи по направлению» c deep-link в `/worklists?domain=…`.

**Out of scope этого spec'а:** содержательное наполнение `/feeding` сверх двух стартовых панелей; редизайн самих страниц `/vet` и `/reproduction`; редизайн `/worklists`; интеграция IoT (P2-3).

**Не-цели:** ослаблять RBAC; ломать существующие deep-links (`/treatments/*` остаётся доступным через redirect); вводить feature-flag — изменения косметико-навигационные, опасности нет.

---

## 2. Архитектура (P1-3a backbone)

### 2.1 Тип навигации

`web_app/lib/navigation.ts` — заменяем плоский `NavigationItem` на discriminated union:

```ts
type NavigationLeaf  = { kind: 'item';  label: string; href: string; minPermissions?: string[] };
type NavigationGroup = {
  kind: 'group';
  label: string;
  defaultHref: string;          // куда вести при клике в collapsed-режиме
  items: NavigationLeaf[];      // ровно один уровень вложенности
  minPermissions?: string[];    // опционально: если задан, требуется И permission, И ≥1 child
};
type NavigationItem  = NavigationLeaf | NavigationGroup;
type NavigationSection = { title: string; items: NavigationItem[] };
```

Глубина ограничена одним уровнем (`items: NavigationLeaf[]`) — тип не позволяет вложенные группы.

### 2.2 Новая структура секций

```
Основное:
  Главная               (item /dashboard)
  Брифинг               (item /daily-summary)
  Инсайты               (item /insights, perm: alerts.*)
  Аналитика             (item /analytics, perm: reports.*)
  Лента событий         (item /timeline)
  Стадо                 (group, defaultHref=/profiles/animal):
    ├─ Животные          (item /profiles/animal)
    ├─ Воспроизводство   (item /reproduction,   perm: kpi.view)
    ├─ Ветеринария       (item /vet,             perm: kpi.view)
    └─ Кормление         (item /feeding,         perm: kpi.view)
  Помощник              (item /copilot, perm: assistant.ask)

Управление:
  Задачи                (item /worklists)
  Решения               (item /decisions)
  Экономика             (item /economics)

Сервисы:
  (без изменений)
```

Воспроизводство и Ветеринария **переезжают** из «Управления» под «Стадо» — единый источник правды, дублирования нет.

### 2.3 `pathLabels`

Собирается рекурсивно: обход `sections → items → (если group) items[i]`. Уже регистрируемые external labels (`/admin/ai`, `/settings`, `/connections`) сохраняются. Запись `/treatments → 'Лечение'` удаляется (стр. живёт как таб внутри `/vet`; pathLabels для `/vet?tab=withdrawal` не нужен — берётся label `/vet`).

### 2.4 Sidebar (`web_app/components/app/sidebar.tsx`)

- **Item** — как сейчас: `<Link>` с иконкой и активным состоянием.
- **Group** — `<button>` c label + `ChevronDown/Right`; по клику toggle open-state. При group-открытии под кнопкой рендерятся дочерние items (стандартный паттерн Radix collapsible).
- **Open-state persistence:** `localStorage['nav.groups.open']: string[]` (массив labels). Hydration в `useEffect` (SSR-safe). При первом mount массив дополняется auto-open для всех групп, где `pathname` совпадает с одним из `children.href` (auto-expand для текущего раздела).
- **Active state:** group подсвечивается (тот же стиль, что и активный item), если `pathname` начинается с любого `children.href`.
- **Collapsed sidebar:** `collapsed === true` → у группы рендерится **одна** иконка (по `iconMap[defaultHref]`); клик → `router.push(group.defaultHref)`. Аккордеон в collapsed-режиме не разворачивается (нет визуального места).
- **Permissions:** существующая логика `getNavigationSections` расширяется: group видна только если permissions group'а удовлетворены **И** хотя бы один child прошёл permission-фильтр. Если permissions не указаны на group'е — достаточно хотя бы одного видимого ребёнка.
- **Icons:** для группы «Стадо» — `Beef` (как сейчас у `/profiles/animal`). У каждого child icon берётся из `iconMap[href]` (Repro=HeartPulse, Vet=Stethoscope; для `/feeding` добавляется `Wheat` или `Salad` из lucide).

### 2.5 Тесты (`web_app/tests/navigation.test.ts`)

Добавляются:
- группа со всеми детьми проходит, если permissions есть;
- группа скрыта, если permissions блокируют всех детей;
- `pathLabels` корректно содержит `/profiles/animal`, `/reproduction`, `/vet`, `/feeding`;
- auto-expand: при pathname `/feeding` группа Стадо open;
- toggle: клик по группе меняет open-state в `localStorage`.

---

## 3. P1-3b — `/feeding` каркас

### 3.1 UI

Маршрут: `web_app/app/(protected)/feeding/page.tsx` (новый).

Layout — канон UI shell (как Decisions/Readiness):
- page header «Кормление», breadcrumbs `Стадо › Кормление` (передаваемые в `<AppShell>` если он используется на этих страницах; иначе — локальный header);
- две панели:
  1. **«Рационы по группам»** — table: `group_name | ration_name | dm_kg | last_distribution_at | status`. Источник: `GET /api/app/v1/feeding/rations`. Empty-state: «Рационы ещё не настроены».
  2. **«Группы со снижением потребления»** — list of cards: `group_name | drop_pct | window_days | last_observed_at`. Источник: `GET /api/app/v1/feeding/intake-drops`. Empty-state: «Снижения потребления не выявлены».

### 3.2 Backend

Новый модуль `web_cabinet/feeding_v1.py` + регистрация роутера в `web_cabinet/api_boundary_v1.py`:

- `GET /api/app/v1/feeding/rations`
  - Permissions: `kpi.view` (any-of).
  - Источник: `configs/feeding/rations_v1.yaml` (data-driven, не хардкод в коде; см. `feedback_no_hardcoded_logic` в memory).
  - Если файла нет / пуст: `{items: []}`.
  - Response: `{ items: FeedingRation[] }`, где `FeedingRation = { group_id, group_name, ration_name, dm_kg, last_distribution_at, status }`.

- `GET /api/app/v1/feeding/intake-drops`
  - Permissions: `kpi.view`.
  - Источник: существующий insight-engine. Фильтр по `insight.kind in ('feed_intake_drop','dmi_drop')` (имена проверить в `src/genomeai/insights/`; если другие — задокументировать). Маппинг: `group_id` берётся из `insight.context.group_id` (или сходного поля), `drop_pct` из `insight.metrics.drop_pct`, `window_days` из `insight.window_days`, `last_observed_at` из `insight.observed_at`.
  - Если такого `kind`'а сейчас нет в системе: возвращаем пустой массив + однократный `logger.info(...)` при boot (не падать; не ломать гейты).
  - Response: `{ items: FeedIntakeDrop[] }`.

### 3.3 Контракты

- `packages/contracts/feeding_v1.py` — Python pydantic-модели `FeedingRation`, `FeedIntakeDrop`, `FeedingRationsResponse`, `FeedIntakeDropsResponse`.
- `packages/contracts/feeding_v1.ts` — TS-эквиваленты.
- `web_app/lib/api/contracts.ts` — re-export новых типов из `feeding_v1`.
- Регистрация двух endpoint'ов в `docs/public_interfaces.json` (как существующие `/api/app/v1/recommended-tasks` и `/api/app/v1/worklists/from-recommended`).

### 3.4 Конфиг

`configs/feeding/rations_v1.yaml` (новый, пустой каркас):
```yaml
version: 1
groups: []   # пример:
             # - group_id: GR-01
             #   group_name: "Группа 1 (сухостой)"
             #   ration_name: "Сухостой 30 кг СВ"
             #   dm_kg: 14.5
             #   last_distribution_at: "2026-05-15T06:30:00Z"
             #   status: ok
```

### 3.5 Acceptance

- `GET /api/app/v1/feeding/rations` → 200 + пустой массив на чистой ферме; 200 + items, если в yaml есть данные.
- `GET /api/app/v1/feeding/intake-drops` → 200 + пустой массив (insight-engine пока без feed_intake_drop).
- Страница `/feeding` открывается без ошибок, обе панели рисуют empty-state, нет 404/500 в network tab.
- Без `kpi.view` permission — 403 на оба endpoint'а, страница `/feeding` редиректит / показывает «нет доступа» (стандартный pattern protected layout).

---

## 4. P1-3c — Таб «Каренция» внутри `/vet`

### 4.1 UI рефакторинг

`web_app/app/(protected)/vet/page.tsx` → layout с tabs (`@radix-ui/react-tabs` через shadcn). Табы:
1. **Обзор** — текущий контент `/vet/page.tsx`, выносится в `web_app/components/vet/tabs/overview-tab.tsx`.
2. **Каренция** — контент текущего `/treatments/page.tsx`, выносится в `web_app/components/vet/tabs/withdrawal-tab.tsx`.
3. **Задачи** — заглушка под P1-3d (см. ниже); первая итерация рендерит summary-card.

URL-стейт активного таба — `?tab=overview|withdrawal|tasks`, дефолт — `overview`. Реализация через `useSearchParams` + `router.replace` без полного reload (Next.js best practice).

### 4.2 Redirect старого URL

`web_app/app/(protected)/treatments/page.tsx` заменяется на server-side redirect:
```tsx
import { redirect } from 'next/navigation';
export default function TreatmentsRedirect() {
  redirect('/vet?tab=withdrawal'); // 308 permanent
}
```

`web_app/lib/navigation.ts`: запись `'/treatments': 'Лечение'` удаляется из `extraPathLabels`. Любой код, генерирующий ссылки на `/treatments`, не ломается — браузер перейдёт на /vet через 308.

### 4.3 Tests

Playwright smoke (`web_app/tests/e2e/treatments-redirect.spec.ts`):
- `GET /treatments` → 308, location `/vet?tab=withdrawal`;
- следующий запрос → `/vet?tab=withdrawal` отрисовывает содержимое старого `/treatments`.

Также: smoke на `/vet` → дефолтный таб = «Обзор».

---

## 5. P1-3d — «Задачи по направлению» summary-card

### 5.1 UI компонент

`web_app/components/operations/tasks-by-domain-card.tsx`:

```
Props:
  domain: 'health' | 'repro' | string
  title?: string  (default 'Задачи по направлению')
```

Render:
- header (title + domain label),
- counters row: `Открытых N · Просрочено SLA M · На сегодня K`,
- list (top 5 by `due_at asc`): label + status badge + due_at,
- CTA `<Link href={`/worklists?domain=${domain}`}>Открыть все в Задачах →</Link>`.

Источник данных: `GET /api/app/v1/worklists?domain={domain}&limit=5&sort=due_at` — расширенный existing endpoint.

### 5.2 Backend

`web_cabinet/worklists_v1.py`:
- `GET /api/app/v1/worklists` принимает дополнительный query-param `domain: Optional[str]`.
- Если задан — фильтр на серверном уровне по полю `task.domain` (есть в БД tasks_v1; см. `src/core/workflow/tasks.py`).
- Если не задан — поведение неизменное.

Domain-маппинг — без хардкода в UI: `/vet` → `'health'`, `/reproduction` → `'repro'`. Маппинг прописывается **в одном месте** — `web_app/lib/operations/domain-map.ts` (data-driven константа: `PAGE_DOMAIN_MAP: { '/vet': 'health', '/reproduction': 'repro' }`). UI-страница передаёт уже резолвленный domain в `tasks-by-domain-card`.

### 5.3 Размещение

- `/vet?tab=tasks` — внутри таба «Задачи» рендерится `<TasksByDomainCard domain="health" />`.
- `/reproduction/page.tsx` — внизу страницы добавляется `<TasksByDomainCard domain="repro" />`.

### 5.4 Frontend `/worklists`

`web_app/app/(protected)/worklists/page.tsx`:
- читает `?domain=…` через `useSearchParams`,
- если задан — применяет к локальному фильтру (то же поведение, что user может выставить вручную),
- редизайн страницы не делается; добавляется только resolve-фильтра-из-URL и небольшой banner «Фильтр: домейн = …» с кнопкой «Сбросить».

### 5.5 Acceptance

- На `/vet?tab=tasks` карточка показывает счётчики и список задач домена `health`.
- Клик «Открыть все» → `/worklists?domain=health`, фильтр виден в UI.
- На пустом домене — empty-state, ноль не считается ошибкой.
- API `GET /api/app/v1/worklists?domain=health` фильтрует на сервере (verifiable через сравнение с unfiltered → меньше элементов).

---

## 6. Контракт-обновления и гейты

| Файл | Изменение | Когда |
|---|---|---|
| `docs/public_interfaces.json` | +2 endpoint feeding | P1-3b |
| `docs/public_interfaces.json` | +1 query-param на /worklists | P1-3d |
| `packages/contracts/feeding_v1.{py,ts}` | new | P1-3b |
| `configs/feeding/rations_v1.yaml` | new (пустой каркас) | P1-3b |
| `web_app/lib/navigation.ts` | type change + struct change | P1-3a |
| `web_app/components/app/sidebar.tsx` | render group | P1-3a |
| `web_app/tests/navigation.test.ts` | новые кейсы | P1-3a |

**Гейты** (CLAUDE.md §4):
- P1-3a (только frontend): TS + lint + ручной browser smoke + jest на `navigation.test.ts`. Поскольку 7 гейтов CLAUDE.md §4 не прогнаны, статус P1-3a ограничен `partially_proven`; полные гейты прогоняем на ближайшем backend-инкременте (P1-3b).
- P1-3b: все 7 гейтов CLAUDE.md §4 (новые endpoints + контракт). Дополнительно — web smoke в браузере на пустых данных.
- P1-3c: TS + Playwright smoke на redirect; runtime-проверка на `/vet?tab=withdrawal`.
- P1-3d: все 7 гейтов CLAUDE.md §4 (изменение API filter).

Каждому инкременту — свой proof-файл: `docs/iterations/T34-P1-3{a,b,c,d}_execution_proof.md` по шаблону `T34-09_execution_proof.md`.

---

## 7. Риски и допущения

1. **Insight kind `feed_intake_drop` может отсутствовать** в текущем insight-engine. Допущение: backend graceful — пустой массив + однократный log. **Не блокер.**
2. **Domain `health` vs `vet`** — в `task_domain_map.yaml` Ветеринария маппится в `health` (не `vet`). Это интуитивно неочевидно. Документируем в комментарии в `domain-map.ts`.
3. **`?tab=…` query-param** на /vet — потенциально конфликтует с любыми внутренними фильтрами /vet (если такие есть). Проверить при имплементации; если есть — переименовать наш параметр в `?vetTab=…`.
4. **localStorage в SSR** — sidebar нельзя читать localStorage до hydration. Решение: первый рендер с пустым open-state, затем `useEffect` подтягивает + auto-expand по pathname. Возможный мигающий «closed → open» переход — допустим (sidebar и так client-only).
5. **Permissions на новом /feeding** — выбран `kpi.view` по аналогии с /vet и /reproduction. Если пользователю с `kpi.view`, но без feeding-specific прав, кормление не должно быть доступно — пометить в RBAC backlog и адресовать в P1-5 (IAM-матрица), но не блокировать P1-3.
6. **Старый `/treatments` deep-link в обучающих материалах** — координатор подтвердил оставить как redirect (см. backlog §4 п.1). Проверки на ломку нет: 308 = браузер-навигация работает; SEO-сниппеты ломаться не должны.

---

## 8. Деливераблы (summary)

**P1-3a — Navigation accordion:**
- `web_app/lib/navigation.ts` — discriminated union + новая структура секций.
- `web_app/components/app/sidebar.tsx` — рендер групп, localStorage, auto-expand.
- `web_app/tests/navigation.test.ts` — расширенные кейсы.
- Иконка `Wheat` для `/feeding` (lucide).

**P1-3b — /feeding скелет:**
- `web_cabinet/feeding_v1.py` (новый роутер) + регистрация в `api_boundary_v1.py`.
- `packages/contracts/feeding_v1.{py,ts}`, обновление `web_app/lib/api/contracts.ts`.
- `configs/feeding/rations_v1.yaml` (пустой).
- `web_app/app/(protected)/feeding/page.tsx`.
- `docs/public_interfaces.json` — +2 endpoint'а.

**P1-3c — Таб Каренция:**
- `web_app/app/(protected)/vet/page.tsx` — layout с tabs.
- `web_app/components/vet/tabs/{overview-tab,withdrawal-tab}.tsx`.
- `web_app/app/(protected)/treatments/page.tsx` — replaced redirect.
- `web_app/lib/navigation.ts` — убираем `/treatments` из `extraPathLabels`.
- Playwright smoke spec на redirect.

**P1-3d — Tasks-by-domain:**
- `web_cabinet/worklists_v1.py` — query-param `domain`.
- `web_app/lib/operations/domain-map.ts`.
- `web_app/components/operations/tasks-by-domain-card.tsx`.
- `web_app/app/(protected)/vet/page.tsx` — таб «Задачи» с карточкой.
- `web_app/app/(protected)/reproduction/page.tsx` — карточка внизу.
- `web_app/app/(protected)/worklists/page.tsx` — чтение `?domain=…`.

---

**Готов следующий шаг:** writing-plans для P1-3a (отдельный imeplementation plan), затем последовательно — для P1-3b/c/d.
