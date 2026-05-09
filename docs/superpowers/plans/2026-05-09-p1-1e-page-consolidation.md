# P1-1e Page Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the protected page set from 27 routes to 21 by consolidating 4 active duplicates into their canonical targets and deleting 2 truly dead pages, so every reachable page is in the sidebar and there is one canonical surface per user-facing concept.

**Architecture:** Each consolidation pair gets feature parity ported into the target page (or a tab inside it), then the source page deleted, then every outbound link updated. The two dead pages (`/design-system`, `/weekly-brief`) are deleted outright since they have zero references.

**Tech Stack:** Next.js 15 (App Router), React 19, TypeScript 5.8, Playwright (manual smoke).

**Source brief:** Conversation 2026-05-09: user request "удалим эти мертвые страницы" → "Полная консолидация" → "Планируем полную консолидацию P1-1e". Audit results in plan §1 below.

**Commit strategy (CLAUDE.md §3):** 7 commits — one per phase + final proof. No DB migrations, no golden updates.

---

## §1 Consolidation pairs and feature parity audit

| Source | Target | What target needs to gain | Outbound links to rewrite |
|---|---|---|---|
| `/alerts` | `/insights` | URL filter params (severity, status, farm); accept loss of separate FilterBar UI since insights already has triage tabs | 3 — `attention-card.tsx`, `daily-operations-dashboard.tsx` (×2) |
| `/planner` | `/timeline` | Weekly plans block (table) and pending-approvals counter as a top-of-page section above the event feed | 3 — `daily-operations-dashboard.tsx`, `worklists-surface.tsx`, `reproduction-surface.tsx` |
| `/reports` | `/analytics` | Reports tab containing catalog + view + governance; existing analytics tabs unchanged | 5+ — `planner-surface.tsx` (will be deleted), `report-view-surface.tsx` (self), `report-catalog-surface.tsx` (self), plus internal report module imports |
| `/assistant` | `/copilot` | `?target=<URL>&data_version=...&task_id=...` query parser that switches /copilot into "explain" mode for the resolved target | 10+ — `worklist-list.tsx`, `alert-list.tsx`, `assistant-entry-points.tsx`, several deep-link callers |
| `/design-system` | (delete) | n/a | 0 |
| `/weekly-brief` | (delete) | n/a | 0 |

### Decisions taken at plan time

1. **`/alerts` → `/insights`**: do NOT port `AlertsSurface` filter UI verbatim. Instead, accept feature loss for the standalone filter bar; let `/insights` triage tabs handle the same UX. URL params support added so deep-linked filters from outside the app survive. Rationale: `AlertsSurface`'s value-add is the alert-card row format with reasons/badges — that exists in `/insights` already.

2. **`/planner` → `/timeline`**: port `PlannerSurface` as a NEW collapsible "Недельные планы" section at the top of `/timeline`. Keep its own data fetch (`/api/planner`) and its own loading/error state. Don't try to merge with timeline events. Rationale: weekly plans + event feed are complementary — operators want both visible together, not in separate routes.

3. **`/reports` → `/analytics`**: port reports as a new top-level tab inside `/analytics`. Existing analytics tabs stay. Reports sub-routes (`/reports/[data_version]/[report_version]`) become `/analytics?tab=reports&data_version=X&report_version=Y` via query params.

4. **`/assistant` → `/copilot`**: extend `/copilot` to accept `?target=<encoded URL>&task_id=&object_id=&...`. When target is present, /copilot renders an "Explain mode" panel above the chat that parses the target URL and shows the AssistantInteractiveClient output, with the chat preserved below. Rationale: explain-deep-link is a different UX from free-form chat but they share the same product (AI assistant for the farm).

5. **Route shims for graceful fallback**: each deleted source page replaced with a one-line `redirect('/<target>')` (Next.js `redirect()` from `next/navigation`) BEFORE the page directory is fully deleted, so external bookmarks / browser history don't 404. The redirect lives for one release cycle, then the directory is removed in Phase 6 cleanup.

---

## Phase 1 — Delete truly-dead pages (1 commit)

**Files:**
- Delete: `web_app/app/(protected)/design-system/` (entire directory)
- Delete: `web_app/app/(protected)/weekly-brief/` (entire directory)

- [ ] **Step 1: Confirm zero references** — already verified during plan write-up:
  ```bash
  grep -rn 'href="/design-system\|href="/weekly-brief\|/design-system"\|/weekly-brief"' web_app/ --include='*.tsx' --include='*.ts' | grep -v node_modules | grep -v '\.next' | grep -v 'app/(protected)/design-system' | grep -v 'app/(protected)/weekly-brief'
  ```
  Expected: empty.

- [ ] **Step 2: Delete the two directories**
  ```bash
  rm -rf web_app/app/\(protected\)/design-system
  rm -rf web_app/app/\(protected\)/weekly-brief
  ```

- [ ] **Step 3: Verify no related component imports break**
  ```bash
  grep -rn 'from.*design-system\|/weekly-brief' web_app/ --include='*.tsx' --include='*.ts' | grep -v node_modules | grep -v '\.next'
  ```
  - `web_app/components/overview/weekly-brief-card.tsx` imports `lib/api/weekly-brief` (the API client, not the page route). That's fine — keep the component, it's used on the dashboard.
  - Anything else: investigate.

- [ ] **Step 4: TypeScript check**
  ```bash
  cd web_app && npx tsc --noEmit
  ```

- [ ] **Step 5: Commit**
  ```bash
  git add -A web_app/app/\(protected\)/
  git commit -m "$(cat <<'EOF'
  chore(P1-1e): remove dead /design-system and /weekly-brief pages

  Both pages had zero outbound href references in the repo (verified
  via grep). /design-system was a dev-only design system reference
  page; /weekly-brief had no reachable sidebar/link entry — its
  component (weekly-brief-card.tsx) is used on the dashboard and
  stays.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Phase 2 — Consolidate `/alerts` → `/insights` (1 commit)

**Files:**
- Modify: `web_app/app/(protected)/insights/page.tsx` — accept URL params via `useSearchParams`
- Modify: `web_app/components/overview/attention-card.tsx:48` — change href
- Modify: `web_app/components/operations/daily-operations-dashboard.tsx:126,294` — change hrefs
- Replace: `web_app/app/(protected)/alerts/page.tsx` body with `redirect('/insights')`

- [ ] **Step 1: Add URL param support to `/insights`**

  Read `web_app/app/(protected)/insights/page.tsx`. If it doesn't already use `useSearchParams`, add it client-side (the page is `'use client'` already per existing patterns):
  ```tsx
  'use client';
  import { useSearchParams } from 'next/navigation';
  // ...
  export default function InsightsPage() {
    const sp = useSearchParams();
    const initialFilter = {
      severity: sp.get('severity') || undefined,
      status: sp.get('status') || undefined,
      farm: sp.get('farm') || undefined,
    };
    // pass to existing triage-tab state initializer
  }
  ```

  If page is server component, convert the filter logic into a child client component that receives the parsed initial filter as a prop.

- [ ] **Step 2: Replace `/alerts` page body with redirect**
  ```tsx
  // web_app/app/(protected)/alerts/page.tsx
  import { redirect } from 'next/navigation';
  export default function AlertsPageRedirect() {
    redirect('/insights');
  }
  ```
  Delete `web_app/components/operations/alerts-surface.tsx` (no longer used).

- [ ] **Step 3: Update outbound hrefs to `/alerts`**

  - `web_app/components/overview/attention-card.tsx:48`:
    ```diff
    - href="/alerts"
    + href="/insights"
    ```
  - `web_app/components/operations/daily-operations-dashboard.tsx:126`:
    ```diff
    - <Link className="linked-action-card" href="/alerts">
    + <Link className="linked-action-card" href="/insights">
    ```
  - `web_app/components/operations/daily-operations-dashboard.tsx:294`: same.
  - `web_app/components/operations/alert-list.tsx`: deep-link `/alerts?...` if any — replace with `/insights?...` preserving query params.

- [ ] **Step 4: TS check + manual smoke**

  ```bash
  cd web_app && npx tsc --noEmit
  ```

  Manually verify in dev: hard-reload `/`, click "Open alerts" linked-action → must land on `/insights` with the same context. Click an alert from attention-card → also `/insights`.

- [ ] **Step 5: Commit**
  ```bash
  git commit -m "feat(P1-1e): consolidate /alerts into /insights

  - Convert /alerts to a one-line redirect('/insights')
  - Delete components/operations/alerts-surface.tsx (orphan)
  - Update 3 outbound hrefs (/alerts → /insights)
  - Add ?severity / ?status / ?farm URL params to /insights so
    cross-page deep-links survive the rename

  AlertsSurface's standalone FilterBar is dropped; /insights triage
  tabs cover the same triage UX. Filter state from external bookmarks
  preserved via the new URL params.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
  ```

---

## Phase 3 — Consolidate `/planner` → `/timeline` (1 commit)

**Files:**
- Modify: `web_app/app/(protected)/timeline/page.tsx` — add weekly plans section
- Move: `web_app/components/operations/planner-surface.tsx` → `web_app/components/timeline/weekly-plans-section.tsx` (new file, simplified — just the weekly plans table + approvals counter, NOT the Daily Brief Preview which already exists elsewhere)
- Modify: `web_app/components/operations/daily-operations-dashboard.tsx:310` — href to /timeline
- Modify: `web_app/components/operations/worklists-surface.tsx` — href to /timeline
- Modify: `web_app/components/extended/reproduction-surface.tsx:54` — href to /timeline
- Replace: `web_app/app/(protected)/planner/page.tsx` body with `redirect('/timeline')`
- Delete: `web_app/components/operations/planner-surface.tsx` (after extracting useful parts)

- [ ] **Step 1: Extract weekly plans + approvals into a focused component**

  Create `web_app/components/timeline/weekly-plans-section.tsx`:
  ```tsx
  'use client';
  import { useEffect, useState } from 'react';
  import { Card, MetricCard } from '@/components/ui/card';
  import { apiFetch } from '@/lib/api';
  import type { PlannerResponse } from '@/lib/api/contracts';

  export function WeeklyPlansSection() {
    const [data, setData] = useState<PlannerResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      apiFetch<PlannerResponse>('/planner')
        .then(setData)
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, []);

    if (error) return <div className="card error-text">Не удалось загрузить недельные планы: {error}</div>;
    if (!data) return null;
    return (
      <Card>
        <h3 className="card-title">Недельные планы</h3>
        <div className="grid grid-3">
          <MetricCard title="Открытых задач" value={data.summary.tasks_open} />
          <MetricCard title="Просроченных" value={data.summary.overdue_active} />
          <MetricCard title="Ожидают подтверждения" value={data.pending_approvals} />
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Название</th><th>Статус</th><th>Начало недели</th><th>Задач</th><th>Ферма</th></tr>
            </thead>
            <tbody>
              {data.weekly_plans.map((plan) => (
                <tr key={plan.plan_id}>
                  <td>{plan.name}</td>
                  <td>{plan.status}</td>
                  <td>{plan.week_start}</td>
                  <td>{plan.item_count}</td>
                  <td>{plan.farm_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    );
  }
  ```

- [ ] **Step 2: Add the section to `/timeline` page**

  Modify `web_app/app/(protected)/timeline/page.tsx` — render `<WeeklyPlansSection />` above the existing event feed.

- [ ] **Step 3: Replace `/planner` page body with redirect**
  ```tsx
  import { redirect } from 'next/navigation';
  export default function PlannerPageRedirect() { redirect('/timeline'); }
  ```

- [ ] **Step 4: Delete `web_app/components/operations/planner-surface.tsx`**

- [ ] **Step 5: Update 3 outbound hrefs from /planner → /timeline**

- [ ] **Step 6: TS check, dev-smoke, commit**

  Smoke: open /timeline — Weekly Plans card visible at the top with overdue/approvals metrics and table. Open /planner → 308 redirect to /timeline.

  ```bash
  git commit -m "feat(P1-1e): consolidate /planner into /timeline

  Move weekly plans table + approvals counter into a new component
  components/timeline/weekly-plans-section.tsx and render it above
  the existing event feed on /timeline. Convert /planner to a
  redirect.

  Drops the standalone DailyBriefPreview that planner-surface
  rendered — that view stays available on the dashboard and via
  /daily-summary, so timeline doesn't duplicate it.

  Updates 3 outbound hrefs.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
  ```

---

## Phase 4 — Consolidate `/reports` → `/analytics` (1 commit)

This is the largest phase — `/reports` is a complete sub-module with catalog, view, governance.

**Files:**
- Modify: `web_app/app/(protected)/analytics/page.tsx` — add a "Reports" top-level tab
- Move: `web_app/components/reports/*` → `web_app/components/analytics/reports/*` (rename directory)
- Update import paths in moved files
- Modify: `web_app/lib/api/profiles-reports-assistant.ts` — keep API helpers, no path change
- Replace: `web_app/app/(protected)/reports/page.tsx` body with `redirect('/analytics?tab=reports')`
- Replace: `web_app/app/(protected)/reports/[data_version]/[report_version]/page.tsx` body with `redirect('/analytics?tab=reports&data_version=...&report_version=...')`

- [ ] **Step 1: Add `?tab=reports` URL handling to `/analytics`**

  Read existing analytics page to see how it switches tabs (likely already has tab state). Add `'reports'` to the tab enum, render `<ReportCatalogSurface />` (or `<ReportViewSurface />` if `data_version`+`report_version` query params present) inside the new tab.

- [ ] **Step 2: Move components/reports → components/analytics/reports**
  ```bash
  git mv web_app/components/reports web_app/components/analytics/reports
  ```

  Update internal imports in moved files (cross-import paths from `@/components/reports/...` → `@/components/analytics/reports/...`).

- [ ] **Step 3: Replace `/reports` page bodies with redirects**

  `web_app/app/(protected)/reports/page.tsx`:
  ```tsx
  import { redirect } from 'next/navigation';
  export default function ReportsPageRedirect() { redirect('/analytics?tab=reports'); }
  ```

  `web_app/app/(protected)/reports/[data_version]/[report_version]/page.tsx`:
  ```tsx
  import { redirect } from 'next/navigation';
  export default async function ReportsViewRedirect({ params }: { params: Promise<{ data_version: string; report_version: string }> }) {
    const { data_version, report_version } = await params;
    redirect(`/analytics?tab=reports&data_version=${encodeURIComponent(data_version)}&report_version=${encodeURIComponent(report_version)}`);
  }
  ```

- [ ] **Step 4: Update outbound hrefs**

  All `/reports` and `/reports/...` hrefs to `/analytics?tab=reports[&...]`.

- [ ] **Step 5: TS check, dev-smoke, commit**

  Smoke: `/analytics` has a Reports tab; clicking opens catalog; clicking a report row opens the view; governance/approve actions work; old `/reports/<dv>/<rv>` URL still works (redirect).

---

## Phase 5 — Consolidate `/assistant` → `/copilot` (1 commit)

This is the trickiest phase — `/assistant` accepts deep-link query params that resolve to specific contexts (alerts, worklists, fact_pack).

**Files:**
- Modify: `web_app/app/(protected)/copilot/page.tsx` — accept `?target=` and `?explain_*=` query params; render an Explain panel when present
- Move: `web_app/components/operations/assistant-interactive-client.tsx` → `web_app/components/copilot/explain-panel.tsx`
- Move: `web_app/components/assistant/assistant-entry-points.tsx` → `web_app/components/copilot/explain-entry-points.tsx`
- Replace: `web_app/app/(protected)/assistant/page.tsx` body with redirect that preserves query string
- Update 10+ outbound hrefs

- [ ] **Step 1: Read /copilot page and AssistantInteractiveClient**

  Identify how `AssistantInteractiveClient` parses `target` URL. Decide whether to render Explain panel ABOVE the chat or as a switchable mode.

  Decision: render as a collapsible card at the top of /copilot. Chat stays below.

- [ ] **Step 2: Add Explain mode to /copilot**

  ```tsx
  'use client';
  import { useSearchParams } from 'next/navigation';
  import { ExplainPanel } from '@/components/copilot/explain-panel';
  // ...
  export default function CopilotPage() {
    const sp = useSearchParams();
    const target = sp.get('target');
    return (
      <>
        {target && <ExplainPanel target={target} sp={sp} />}
        {/* existing chat UI */}
      </>
    );
  }
  ```

- [ ] **Step 3: Replace `/assistant` page with redirect that preserves query**

  ```tsx
  import { redirect } from 'next/navigation';
  export default async function AssistantRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
    const params = await searchParams;
    const qs = new URLSearchParams(
      Object.entries(params).flatMap(([k, v]) =>
        Array.isArray(v) ? v.map((x) => [k, String(x)]) : v ? [[k, String(v)]] : []
      ),
    );
    const suffix = qs.toString();
    redirect(`/copilot${suffix ? `?${suffix}` : ''}`);
  }
  ```

- [ ] **Step 4: Update 10+ deep-link hrefs**

  In `worklist-list.tsx`, `alert-list.tsx`, `assistant-entry-points.tsx`, etc. — replace `/assistant?target=...` with `/copilot?target=...`.

- [ ] **Step 5: Delete `web_app/components/assistant/` directory** (contents moved in step 1).

- [ ] **Step 6: TS check, smoke, commit**

  Smoke: From /worklists, click "Explain" on a task → /copilot opens with the explain panel populated for that task; the chat below also works. Old /assistant?target=... URL still works (redirect preserves query).

---

## Phase 6 — Final cleanup, sidebar nav, CI gates, proof (1 commit)

- [ ] **Step 1: Confirm 4 source pages now live as one-line redirects**

  ```bash
  for p in alerts planner reports assistant; do
    echo "=== /$p ==="
    cat web_app/app/\(protected\)/$p/page.tsx
  done
  ```

  Each must be a thin `redirect()` page.

- [ ] **Step 2: Decide whether to delete redirect shims now or keep one cycle**

  Keep them for one release. Document the deprecation in `docs/deprecation_policy.md` with a removal target date (e.g., 2026-06-09).

- [ ] **Step 3: Remove `/admin/ai` from sidebar?**

  No — added in commit 6670be2 and is correct. Leave alone.

- [ ] **Step 4: Sidebar still works** — no changes needed since the source paths are still valid (just redirect).

- [ ] **Step 5: Run TS check + lint**

  ```bash
  cd web_app && npx tsc --noEmit
  ```

- [ ] **Step 6: Run all 7 CI gates per CLAUDE.md §4**

  Same procedure as P1-1 Phase 6. Capture exit codes; gates 1-4 most likely to catch issues; gates 5-7 less affected.

- [ ] **Step 7: Manual UI smoke**

  Hard-reload browser. From dashboard:
  - Click linked-action "Open alerts" → /insights
  - Click "Open planner" → /timeline (with weekly plans block visible)
  - Open /timeline directly — Weekly Plans card at top
  - Open /analytics → Reports tab → clicking a report opens view
  - From a worklist, click "Explain" → /copilot opens with explain panel
  - Try old URL `/assistant?target=worklists&task_id=ABC` → redirects to /copilot with explain panel populated

  Document any failures in the proof file.

- [ ] **Step 8: Write execution proof**

  Create `docs/iterations/T34-P1-1e_execution_proof.md` with:
  - Source brief reference
  - All 6 phase commits
  - Acceptance table per pair
  - 7 CI gate exits + log excerpts
  - Manual UI smoke matrix (route → action → expected → observed)
  - Honest status (`proven` if all green; `partially_proven` with reasons otherwise)

- [ ] **Step 9: Final commit + push**

  ```bash
  git add docs/iterations/T34-P1-1e_execution_proof.md docs/deprecation_policy.md
  git commit -m "docs(P1-1e): execution proof — page consolidation"
  git push
  ```

---

## Acceptance criteria

- [ ] `/design-system` and `/weekly-brief` page directories deleted
- [ ] `/alerts`, `/planner`, `/reports`, `/assistant` reduced to one-line `redirect()` pages
- [ ] `/insights` accepts `?severity`, `?status`, `?farm` URL params
- [ ] `/timeline` shows Weekly Plans card at top
- [ ] `/analytics` has a Reports tab with full catalog/view/governance
- [ ] `/copilot` accepts `?target=` query param and shows Explain panel
- [ ] All deep-links from worklists/alerts/dashboard route to consolidated targets
- [ ] All 7 CI gates green
- [ ] Manual UI smoke matrix all-green
- [ ] Execution proof committed
- [ ] Status: `proven`

## Out of scope (future)

- Removing the `/alerts` `/planner` `/reports` `/assistant` redirect shims (do in next cycle, after release telemetry shows zero traffic)
- Backend route deprecation: `/api/planner`, `/api/reports/*` continue serving — still consumed by the consolidated pages
- Visual polish of the new `/timeline` Weekly Plans card or `/analytics` Reports tab — port functional parity first, polish later
- Mobile UX on consolidated pages — current tests are desktop-only
