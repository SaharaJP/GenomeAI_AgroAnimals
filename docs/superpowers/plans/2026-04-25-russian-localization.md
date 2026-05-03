# Russian Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all English user-facing strings in the Next.js frontend with Russian equivalents via direct inline substitution.

**Architecture:** Direct string replacement in JSX/TS — no i18n library, no new files, no new dependencies.

**Tech Stack:** Next.js 15, TypeScript, React 19

---

### Task 1: Auth — login page + form

**Files:**
- Modify: `web_app/app/login/page.tsx`
- Modify: `web_app/components/auth/login-form.tsx`

- [ ] Replace in `login/page.tsx`:
  - `"New React / Next.js cabinet foundation. Authentication stays server-backed via backend API."` → `"Система управления молочным стадом. Аутентификация через бэкенд API."`

- [ ] Replace in `login-form.tsx`:
  - `<label>Tenant</label>` → `<label>Организация</label>`
  - `<label>Username</label>` → `<label>Имя пользователя</label>`
  - `<label>Password</label>` → `<label>Пароль</label>`
  - `'Login failed'` → `'Ошибка входа'`
  - `'Signing in…'` → `'Вхожу…'`
  - `'Sign in'` → `'Войти'`

- [ ] Verify: `cd web_app && npx tsc --noEmit` — 0 errors

- [ ] Commit: `git commit -m "feat(i18n): translate auth screens to Russian"`

---

### Task 2: UI primitives — FilterBar + ExplainabilityBlock

**Files:**
- Modify: `web_app/components/ui/filter-bar.tsx`
- Modify: `web_app/components/ui/explainability-block.tsx`

- [ ] Replace in `filter-bar.tsx`:
  - `placeholder='Filter…'` → `placeholder='Фильтр…'`
  - `"All farms"` → `"Все фермы"`
  - `"Active scope"` → `"Активный scope"`
  - `"Today"` → `"Сегодня"`
  - `"This week"` → `"Эта неделя"`
  - `"This month"` → `"Этот месяц"`

- [ ] Replace in `explainability-block.tsx`:
  - `'Why this matters'` → `'Почему это важно'`

- [ ] Commit: `git commit -m "feat(i18n): translate UI primitives to Russian"`

---

### Task 3: Alerts surface + Alert list

**Files:**
- Modify: `web_app/components/operations/alerts-surface.tsx`
- Modify: `web_app/components/operations/alert-list.tsx`

- [ ] Replace in `alerts-surface.tsx`:
  - `"Alerts"` (page-title) → `"Инсайты"`
  - `"Daily triage surface with linked actions..."` → `"Ежедневный мониторинг алертов с привязкой к решениям и объяснениям."`
  - `placeholder="Filter alerts by farm, entity, type or status…"` → `placeholder="Фильтр по ферме, объекту, типу или статусу…"`
  - `"Visible alerts"` → `"Всего алертов"`
  - `"Open"` → `"Открытых"`
  - `"Critical / high"` → `"Критических / высоких"`
  - ExplainabilityBlock reasons → переведены ниже
  - `"Multi-site visibility"` → `"Мультисайтовый просмотр"`
  - `"Current alert slice spans multiple farms/sites..."` → `"Текущий срез алертов охватывает несколько ферм/сайтов."`
  - `"Loading alerts…"` → `"Загружаю алерты…"`
  - ExplainabilityBlock reasons:
    - `'Alert generation stays in backend; React renders only canonical DTOs.'` → `'Алерты генерируются бэкендом; React отображает только канонические DTO.'`
    - `'Decision and feedback hooks remain available from each alert card.'` → `'Действия и обратная связь доступны из каждой карточки алерта.'`
    - `'Farm references preserve single-farm and multi-site daily triage.'` → `'Ссылки на фермы обеспечивают работу в одно- и мультисайтовом режимах.'`

- [ ] Replace in `alert-list.tsx`:
  - `farm {item.entity?.farm_id||'—'}` → `ферма {item.entity?.farm_id||'—'}`
  - `'Explainability is available from backend DTOs.'` → `'Объяснение доступно из backend DTO.'`
  - `confidence {item.confidence.toFixed(2)}` → `уверенность {item.confidence.toFixed(2)}`
  - `>Profile<` → `>Профиль<`
  - `>Explain<` → `>Объяснить<`
  - `>Decision hook<` → `>Решение<`
  - `>Feedback hook<` → `>Обратная связь<`

- [ ] Commit: `git commit -m "feat(i18n): translate alerts surface to Russian"`

---

### Task 4: Scope summary + Worklists surface

**Files:**
- Modify: `web_app/components/operations/scope-summary.tsx`
- Modify: `web_app/components/operations/worklists-surface.tsx`

- [ ] Replace in `scope-summary.tsx`:
  - `"Scope and tenancy"` → `"Область и организация"`
  - `<span>Tenant</span>` → `<span>Организация</span>`
  - `<span>Mode</span>` → `<span>Режим</span>`
  - `<span>Active farm</span>` → `<span>Активная ферма</span>`
  - `'all visible farms'` → `'все видимые фермы'`
  - `<span>Active site</span>` → `<span>Активный сайт</span>`
  - `'all visible sites'` → `'все видимые сайты'`
  - `<span>Visible farms</span>` → `<span>Видимых ферм</span>`
  - `<span>Visible sites</span>` → `<span>Видимых сайтов</span>`

- [ ] Replace in `worklists-surface.tsx`:
  - `"Worklists"` → `"Рабочие списки"`
  - `"Daily execution surface..."` → `"Ежедневные очереди задач с привязкой к действиям и объяснениям."`
  - `placeholder="Filter worklists by farm, task, owner or alert…"` → `placeholder="Фильтр по ферме, задаче, исполнителю или алерту…"`
  - `"Visible tasks"` → `"Всего задач"`
  - `"Open tasks"` → `"Открытых задач"`
  - `"Overdue"` → `"Просроченных"`
  - ExplainabilityBlock reasons → translated
  - `"Loading worklists…"` → `"Загружаю задачи…"`
  - `"Linked action hooks"` → `"Связанные действия"`
  - `"Open planner"` → `"Открыть планировщик"`
  - `"Decision trail"` → `"Журнал решений"`
  - `"Feedback / support"` → `"Обратная связь / поддержка"`

- [ ] Commit: `git commit -m "feat(i18n): translate scope-summary + worklists to Russian"`

---

### Task 5: Daily operations dashboard

**Files:**
- Modify: `web_app/components/operations/daily-operations-dashboard.tsx`

- [ ] Translate all English strings (page title, section titles, table headers, button labels, metric card titles, error messages, linked action captions)

- [ ] Commit: `git commit -m "feat(i18n): translate daily-operations-dashboard to Russian"`

---

### Task 6: Planner surface + Assistant client

**Files:**
- Modify: `web_app/components/operations/planner-surface.tsx`
- Modify: `web_app/components/operations/assistant-interactive-client.tsx`

- [ ] Translate planner-surface (page title, subtitle, metric cards, table headers, links)
- [ ] Translate assistant-interactive-client (explainability reasons, button label, error messages)

- [ ] Commit: `git commit -m "feat(i18n): translate planner + assistant to Russian"`

---

### Task 7: Analytics — chart cards + tabs

**Files:**
- Modify: `web_app/components/analytics/chart-card.tsx`
- Modify: `web_app/components/analytics/health-tab.tsx`
- Modify: `web_app/components/analytics/production-tab.tsx`
- Modify: `web_app/components/analytics/reproduction-tab.tsx`
- Modify: `web_app/components/analytics/add-chart-dialog.tsx`

- [ ] Translate chart-card button aria-labels (Alert → Алерт, Delete → Удалить, Rename → Переименовать)
- [ ] Translate health-tab chart titles and badge labels
- [ ] Translate production-tab chart titles and badge labels
- [ ] Translate reproduction-tab chart titles and badge labels
- [ ] Translate add-chart-dialog METRICS (group names + metric names + descriptions)

- [ ] Commit: `git commit -m "feat(i18n): translate analytics components to Russian"`

---

### Task 8: Report governance panel

**Files:**
- Modify: `web_app/components/reports/report-governance-panel.tsx`

- [ ] Translate all English strings (title, meta labels, buttons, placeholder, error message)

- [ ] Commit: `git commit -m "feat(i18n): translate report governance panel to Russian"`

---

### Task 9: Final verification

- [ ] Run `cd web_app && npx tsc --noEmit` — expect 0 errors
- [ ] Scan for remaining English UI strings: `grep -rn '"[A-Z][a-z]' web_app/components/operations web_app/components/analytics web_app/components/auth web_app/components/reports web_app/components/ui/filter-bar.tsx web_app/components/ui/explainability-block.tsx`
- [ ] Visual check in browser: login, dashboard, alerts, worklists, planner, analytics, assistant
