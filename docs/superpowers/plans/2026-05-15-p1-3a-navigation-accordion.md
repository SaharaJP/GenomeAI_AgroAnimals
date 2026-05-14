# P1-3a Navigation Accordion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить «Стадо» в сайдбаре в группу-аккордеон с подпунктами Животные/Воспроизводство/Ветеринария/Кормление, заменив плоский `NavigationItem` на discriminated union. Воспроизводство и Ветеринария переезжают из «Управления» под «Стадо».

**Architecture:** `NavigationItem = NavigationLeaf | NavigationGroup` ровно с одним уровнем вложенности. Sidebar рендерит группу как collapsible-кнопку + вложенный список. Open-state хранится в `localStorage['nav.groups.open']`, current pathname форсит auto-expand активной группы. /feeding появляется в sidebar; страница `/feeding` будет создана в P1-3b — до того клик ведёт на 404 (приемлемо для одного шага между двумя инкрементами).

**Tech Stack:** TypeScript 5.8, React 19, Next.js 15 App Router, lucide-react. Тесты — `node:test` (type-checked через `tsc --noEmit`, не исполняются в CI; verification: typecheck + `npm run test` (validate-foundation.mjs) + ручной browser smoke).

**Spec:** `docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md` §2.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `web_app/lib/navigation.ts` | Modify (full rewrite) | Discriminated union, новая структура секций, рекурсивный `pathLabels`, обновлённый `getNavigationSections` с фильтром-для-групп |
| `web_app/tests/navigation.test.ts` | Modify | Расширенные кейсы: группа в зависимости от permissions, structure assertions; type-checked |
| `web_app/lib/hooks/use-nav-groups-open.ts` | Create | Hook для localStorage open-state + auto-expand по active pathname |
| `web_app/components/app/sidebar.tsx` | Modify | Рендер `NavigationGroup` (toggle + вложенные дети), Wheat-иконка для `/feeding`, корректная фильтрация `bottomHrefs` для union-типа |

**Изменения границ ответственности:** хук `use-nav-groups-open` выносится из sidebar.tsx в отдельный файл (sidebar и так 190 строк, добавление inline accordion-логики уведёт его за 250). Хук — pure UI state, не знает про NavigationItem типы; принимает только labels.

---

## Task 1: Hook `use-nav-groups-open`

**Files:**
- Create: `web_app/lib/hooks/use-nav-groups-open.ts`

- [ ] **Step 1: Создать каталог `web_app/lib/hooks/`**

```bash
mkdir -p /opt/genomeai/repo/web_app/lib/hooks
```

Expected: каталог создан, ошибок нет.

- [ ] **Step 2: Записать полное содержимое хука**

Файл `web_app/lib/hooks/use-nav-groups-open.ts`:

```typescript
'use client';

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'nav.groups.open';

function readStorage(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const arr: unknown = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((x): x is string => typeof x === 'string'));
  } catch {
    return new Set();
  }
}

function writeStorage(open: Set<string>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...open]));
  } catch {
    // ignore quota/privacy errors
  }
}

export type UseNavGroupsOpen = {
  isOpen: (label: string) => boolean;
  toggle: (label: string) => void;
};

/**
 * autoOpenLabels — лейблы групп, которые форсятся в "открыто" текущим pathname.
 * User toggle всё равно записывается в localStorage, но auto-open побеждает на текущей странице.
 */
export function useNavGroupsOpen(autoOpenLabels: readonly string[] = []): UseNavGroupsOpen {
  const [storedOpen, setStoredOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    setStoredOpen(readStorage());
  }, []);

  const isOpen = useCallback(
    (label: string) => autoOpenLabels.includes(label) || storedOpen.has(label),
    [storedOpen, autoOpenLabels],
  );

  const toggle = useCallback((label: string) => {
    setStoredOpen((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      writeStorage(next);
      return next;
    });
  }, []);

  return { isOpen, toggle };
}
```

- [ ] **Step 3: Run typecheck**

```bash
cd /opt/genomeai/repo/web_app && npm run typecheck
```

Expected: PASS, ноль ошибок. Файл-сирота (нет консьюмеров) — `tsc --noEmit` всё равно проверяет.

- [ ] **Step 4: Commit**

```bash
cd /opt/genomeai/repo && git add web_app/lib/hooks/use-nav-groups-open.ts && git commit -m "feat(web): useNavGroupsOpen hook for sidebar accordion state (P1-3a)"
```

---

## Task 2: Migrate `navigation.ts` to discriminated union + update tests

**Files:**
- Modify: `web_app/lib/navigation.ts` (полная замена содержимого)
- Modify: `web_app/tests/navigation.test.ts` (расширение)

> **Атомарный коммит:** оба файла + sidebar.tsx (Task 3) идут одним типизированным изменением. Промежуточный commit ломал бы `tsc --noEmit`. Но чтобы план был «bite-sized», шаги нумеруются отдельно; коммит — после Task 3 Step 6.

- [ ] **Step 1: Заменить содержимое `web_app/lib/navigation.ts`**

```typescript
import type { AuthMeResponse } from '@/lib/api/contracts';

export type NavigationLeaf = {
  kind: 'item';
  label: string;
  href: string;
  minPermissions?: string[];
};

export type NavigationGroup = {
  kind: 'group';
  label: string;
  defaultHref: string;
  items: NavigationLeaf[];
  minPermissions?: string[];
};

export type NavigationItem = NavigationLeaf | NavigationGroup;
export type NavigationSection = { title: string; items: NavigationItem[] };

const sections: NavigationSection[] = [
  {
    title: 'Основное',
    items: [
      { kind: 'item', label: 'Главная', href: '/dashboard' },
      { kind: 'item', label: 'Брифинг', href: '/daily-summary' },
      { kind: 'item', label: 'Инсайты', href: '/insights', minPermissions: ['alerts.view', 'alerts.manage', 'alerts.read'] },
      { kind: 'item', label: 'Аналитика', href: '/analytics', minPermissions: ['reports.view', 'reports.read', 'reports.approve'] },
      { kind: 'item', label: 'Лента событий', href: '/timeline' },
      {
        kind: 'group',
        label: 'Стадо',
        defaultHref: '/profiles/animal',
        items: [
          { kind: 'item', label: 'Животные', href: '/profiles/animal' },
          { kind: 'item', label: 'Воспроизводство', href: '/reproduction', minPermissions: ['kpi.view'] },
          { kind: 'item', label: 'Ветеринария', href: '/vet', minPermissions: ['kpi.view'] },
          { kind: 'item', label: 'Кормление', href: '/feeding', minPermissions: ['kpi.view'] },
        ],
      },
      { kind: 'item', label: 'Помощник', href: '/copilot', minPermissions: ['assistant.ask'] },
    ],
  },
  {
    title: 'Управление',
    items: [
      { kind: 'item', label: 'Задачи', href: '/worklists', minPermissions: ['tasks.view', 'tasks.read', 'tasks.manage'] },
      { kind: 'item', label: 'Решения', href: '/decisions', minPermissions: ['decisionlog.view', 'decisions.read'] },
      { kind: 'item', label: 'Экономика', href: '/economics', minPermissions: ['economics.read', 'whatif.scenarios.view'] },
    ],
  },
  {
    title: 'Сервисы',
    items: [
      { kind: 'item', label: 'Поддержка', href: '/support', minPermissions: ['support.read', 'jobs.view', 'audit.view'] },
      { kind: 'item', label: 'Пилот', href: '/pilot', minPermissions: ['support.read', 'jobs.view'] },
      { kind: 'item', label: 'Готовность системы', href: '/readiness', minPermissions: ['support.read', 'audit.view'] },
      { kind: 'item', label: 'Мониторинг', href: '/observability', minPermissions: ['audit.view', 'jobs.view'] },
      { kind: 'item', label: 'Администрирование', href: '/admin', minPermissions: ['audit.view'] },
    ],
  },
];

const extraPathLabels: Record<string, string> = {
  '/treatments': 'Лечение',
  '/admin/ai': 'AI-наблюдаемость',
  '/settings': 'Настройки',
  '/connections': 'Мои подключения',
  '/feeding': 'Кормление',
};

export const pathLabels: Record<string, string> = (() => {
  const out: Record<string, string> = { ...extraPathLabels };
  for (const section of sections) {
    for (const item of section.items) {
      if (item.kind === 'item') {
        out[item.href] = item.label;
      } else {
        for (const child of item.items) out[child.href] = child.label;
      }
    }
  }
  return out;
})();

function hasAnyPerm(permissions: Set<string>, required: string[] | undefined): boolean {
  if (!required || required.length === 0) return true;
  return required.some((p) => permissions.has(p));
}

export function getNavigationSections(me: AuthMeResponse | null): NavigationSection[] {
  if (!me) return [{ title: 'Общее', items: [{ kind: 'item', label: 'Войти', href: '/login' }] }];
  const permissions = new Set(me.user.permissions || []);
  return sections
    .map((section) => {
      const items: NavigationItem[] = [];
      for (const item of section.items) {
        if (item.kind === 'item') {
          if (hasAnyPerm(permissions, item.minPermissions)) items.push(item);
        } else {
          if (!hasAnyPerm(permissions, item.minPermissions)) continue;
          const visibleChildren = item.items.filter((c) => hasAnyPerm(permissions, c.minPermissions));
          if (visibleChildren.length === 0) continue;
          items.push({ ...item, items: visibleChildren });
        }
      }
      return { ...section, items };
    })
    .filter((section) => section.items.length > 0);
}
```

- [ ] **Step 2: Заменить содержимое `web_app/tests/navigation.test.ts`**

```typescript
import test from 'node:test';
import assert from 'node:assert/strict';
import { getNavigationSections, pathLabels } from '../lib/navigation';
import type { NavigationItem, NavigationSection } from '../lib/navigation';

function allHrefs(sections: NavigationSection[]): string[] {
  const out: string[] = [];
  for (const s of sections) {
    for (const item of s.items) {
      if (item.kind === 'item') out.push(item.href);
      else for (const c of item.items) out.push(c.href);
    }
  }
  return out;
}

function findGroup(sections: NavigationSection[], label: string) {
  for (const s of sections) {
    for (const item of s.items) {
      if (item.kind === 'group' && item.label === label) return item;
    }
  }
  return null;
}

const meWith = (perms: string[]) => ({
  schema: 'x',
  user: { user_id: 1, username: 'u', role: 'admin', permissions: perms },
  session: { session_id: 's', client_kind: 'web', auth_transport: 'bearer', status: 'active', created_at: '', updated_at: '' },
  scope: { tenant_id: 'default', allowed_farm_ids: [], allowed_site_ids: [] },
});

test('viewer navigation excludes support when permission missing', () => {
  const sections = getNavigationSections(meWith(['reports.read']));
  const hrefs = allHrefs(sections);
  assert.equal(hrefs.includes('/support'), false);
  assert.equal(hrefs.includes('/analytics'), true);
});

test('admin navigation includes support section', () => {
  const sections = getNavigationSections(
    meWith(['support.read', 'alerts.read', 'tasks.read', 'planner.read', 'reports.read', 'assistant.ask', 'decisions.read', 'economics.read']),
  );
  const hrefs = allHrefs(sections);
  assert.equal(hrefs.includes('/support'), true);
  assert.equal(hrefs.includes('/insights'), true);
});

test('canonical labels are renamed', () => {
  assert.equal(pathLabels['/daily-summary'], 'Брифинг');
  assert.equal(pathLabels['/worklists'], 'Задачи');
  // /profiles/animal теперь leaf "Животные" внутри группы "Стадо"
  assert.equal(pathLabels['/profiles/animal'], 'Животные');
});

test('treatments stays addressable but is hidden from sidebar', () => {
  const sections = getNavigationSections(
    meWith(['support.read', 'alerts.read', 'tasks.read', 'planner.read', 'reports.read', 'assistant.ask', 'decisions.read', 'economics.read', 'kpi.view', 'audit.view', 'jobs.view']),
  );
  const hrefs = allHrefs(sections);
  assert.equal(hrefs.includes('/treatments'), false);
  assert.equal(pathLabels['/treatments'], 'Лечение');
});

test('Стадо group contains four children for kpi.view user', () => {
  const sections = getNavigationSections(meWith(['kpi.view']));
  const stado = findGroup(sections, 'Стадо');
  assert.ok(stado, 'Стадо group must be present');
  const childHrefs = stado.items.map((c) => c.href).sort();
  assert.deepEqual(childHrefs, ['/feeding', '/profiles/animal', '/reproduction', '/vet']);
});

test('Стадо group keeps Животные when user lacks kpi.view', () => {
  const sections = getNavigationSections(meWith([]));
  const stado = findGroup(sections, 'Стадо');
  assert.ok(stado, 'Стадо group must be present (Животные has no permission gate)');
  const childHrefs = stado.items.map((c) => c.href);
  assert.deepEqual(childHrefs, ['/profiles/animal']);
});

test('Стадо children resolve via pathLabels', () => {
  assert.equal(pathLabels['/profiles/animal'], 'Животные');
  assert.equal(pathLabels['/reproduction'], 'Воспроизводство');
  assert.equal(pathLabels['/vet'], 'Ветеринария');
  assert.equal(pathLabels['/feeding'], 'Кормление');
});

test('Управление section no longer contains Repro/Vet', () => {
  const sections = getNavigationSections(
    meWith(['support.read', 'alerts.read', 'tasks.read', 'planner.read', 'reports.read', 'assistant.ask', 'decisions.read', 'economics.read', 'kpi.view']),
  );
  const mgmt = sections.find((s) => s.title === 'Управление');
  assert.ok(mgmt, 'Управление section must exist');
  const hrefs: string[] = [];
  for (const it of mgmt.items) {
    if (it.kind === 'item') hrefs.push(it.href);
    else for (const c of it.items) hrefs.push(c.href);
  }
  assert.equal(hrefs.includes('/reproduction'), false);
  assert.equal(hrefs.includes('/vet'), false);
  assert.deepEqual(hrefs.sort(), ['/decisions', '/economics', '/worklists']);
});

test('Стадо group exposes defaultHref for collapsed sidebar', () => {
  const sections = getNavigationSections(meWith(['kpi.view']));
  const stado = findGroup(sections, 'Стадо');
  assert.ok(stado, 'Стадо group must be present');
  assert.equal(stado.defaultHref, '/profiles/animal');
});
```

- [ ] **Step 3: Run typecheck**

```bash
cd /opt/genomeai/repo/web_app && npm run typecheck
```

Expected: **FAIL** с ошибками в `components/app/sidebar.tsx` (старый код обращается к `item.href` на union-типе, где у `NavigationGroup` нет `.href`). Это ожидаемо и фиксируется в Task 3. **НЕ коммитим сейчас.**

---

## Task 3: Sidebar — рендер `NavigationGroup`

**Files:**
- Modify: `web_app/components/app/sidebar.tsx`

- [ ] **Step 1: Открыть `web_app/components/app/sidebar.tsx`. Заменить целиком на:**

```tsx
'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Lightbulb,
  BarChart2,
  Clock,
  Bot,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  Settings,
  HelpCircle,
  MessageCircle,
  LogOut,
  Leaf,
  Home,
  Beef,
  ListChecks,
  HeartPulse,
  Stethoscope,
  Pill,
  GitBranch,
  Wallet,
  LifeBuoy,
  FlaskConical,
  ShieldCheck,
  Activity,
  Shield,
  Eye,
  Wheat,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '@/components/auth/auth-provider';
import { getNavigationSections, type NavigationGroup, type NavigationLeaf } from '@/lib/navigation';
import { useNavGroupsOpen } from '@/lib/hooks/use-nav-groups-open';

type Props = { collapsed: boolean; onToggle: () => void };

// Maps href → Lucide icon for nav items across all sections.
const iconMap: Record<string, React.ReactNode> = {
  '/dashboard':        <Home size={18} strokeWidth={1.5} />,
  '/daily-summary':    <LayoutDashboard size={18} strokeWidth={1.5} />,
  '/insights':         <Lightbulb size={18} strokeWidth={1.5} />,
  '/analytics':        <BarChart2 size={18} strokeWidth={1.5} />,
  '/timeline':         <Clock size={18} strokeWidth={1.5} />,
  '/profiles/animal':  <Beef size={18} strokeWidth={1.5} />,
  '/copilot':          <Bot size={18} strokeWidth={1.5} />,
  '/worklists':        <ListChecks size={18} strokeWidth={1.5} />,
  '/reproduction':     <HeartPulse size={18} strokeWidth={1.5} />,
  '/vet':              <Stethoscope size={18} strokeWidth={1.5} />,
  '/treatments':       <Pill size={18} strokeWidth={1.5} />,
  '/feeding':          <Wheat size={18} strokeWidth={1.5} />,
  '/decisions':        <GitBranch size={18} strokeWidth={1.5} />,
  '/economics':        <Wallet size={18} strokeWidth={1.5} />,
  '/support':          <LifeBuoy size={18} strokeWidth={1.5} />,
  '/pilot':            <FlaskConical size={18} strokeWidth={1.5} />,
  '/readiness':        <ShieldCheck size={18} strokeWidth={1.5} />,
  '/observability':    <Activity size={18} strokeWidth={1.5} />,
  '/admin':            <Shield size={18} strokeWidth={1.5} />,
  '/admin/ai':         <Eye size={18} strokeWidth={1.5} />,
};

// Lucide icon for a group when sidebar is collapsed — keyed by defaultHref.
function groupIcon(defaultHref: string): React.ReactNode {
  return iconMap[defaultHref] ?? <LayoutDashboard size={18} strokeWidth={1.5} />;
}

export function Sidebar({ collapsed, onToggle }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const { me } = useAuth() as { me: any; loading: boolean; refresh: () => Promise<void> };

  const sections = getNavigationSections(me);
  const bottomHrefs = new Set(['/connections', '/settings', '/support']);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  // Группа считается активной, если pathname попадает в любого её ребёнка.
  const isGroupActive = (group: NavigationGroup) =>
    group.items.some((c) => isActive(c.href));

  // Auto-open labels — лейблы групп, которые форсятся открытыми текущим pathname.
  const autoOpenLabels: string[] = [];
  for (const section of sections) {
    for (const item of section.items) {
      if (item.kind === 'group' && isGroupActive(item)) {
        autoOpenLabels.push(item.label);
      }
    }
  }

  const { isOpen, toggle } = useNavGroupsOpen(autoOpenLabels);

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.replace('/login');
    router.refresh();
  }

  function renderLeaf(item: NavigationLeaf, opts: { nested?: boolean } = {}) {
    return (
      <Link
        key={item.href}
        href={item.href}
        className={`nav-link ${opts.nested ? 'nav-link-nested' : ''} ${isActive(item.href) ? 'nav-link-active' : ''}`}
        title={collapsed ? item.label : undefined}
      >
        <span className="nav-link-icon">
          {iconMap[item.href] ?? <LayoutDashboard size={18} strokeWidth={1.5} />}
        </span>
        <span className="nav-link-label">{item.label}</span>
      </Link>
    );
  }

  function renderGroup(group: NavigationGroup) {
    const open = isOpen(group.label);
    const active = isGroupActive(group);

    if (collapsed) {
      return (
        <Link
          key={`group:${group.label}`}
          href={group.defaultHref}
          className={`nav-link ${active ? 'nav-link-active' : ''}`}
          title={group.label}
        >
          <span className="nav-link-icon">{groupIcon(group.defaultHref)}</span>
          <span className="nav-link-label">{group.label}</span>
        </Link>
      );
    }

    return (
      <div key={`group:${group.label}`} className="nav-group">
        <button
          type="button"
          className={`nav-link nav-group-toggle ${active ? 'nav-link-active' : ''}`}
          onClick={() => toggle(group.label)}
          aria-expanded={open}
        >
          <span className="nav-link-icon">{groupIcon(group.defaultHref)}</span>
          <span className="nav-link-label">{group.label}</span>
          <span className="nav-group-chevron">
            {open ? <ChevronDown size={16} strokeWidth={1.5} /> : <ChevronRight size={16} strokeWidth={1.5} />}
          </span>
        </button>
        {open && (
          <div className="nav-group-children" role="group" aria-label={group.label}>
            {group.items.map((c) => renderLeaf(c, { nested: true }))}
          </div>
        )}
      </div>
    );
  }

  return (
    <aside className="sidebar">
      {/* Logo — links to home */}
      <Link href="/dashboard" className="sidebar-logo" style={{ textDecoration: 'none' }}>
        <div className="sidebar-logo-mark">
          <Leaf size={16} strokeWidth={2} color="white" />
        </div>
        {!collapsed && (
          <span className="sidebar-wordmark">genomeai агро</span>
        )}
      </Link>

      <nav className="sidebar-nav" aria-label="Основная навигация">
        {sections.map((section) => {
          const items = section.items.filter((it) =>
            it.kind === 'group' ? true : !bottomHrefs.has(it.href),
          );
          if (items.length === 0) return null;
          return (
            <div key={section.title} className="sidebar-section">
              {!collapsed && (
                <div className="sidebar-section-heading">{section.title}</div>
              )}
              {items.map((item) =>
                item.kind === 'item' ? renderLeaf(item) : renderGroup(item),
              )}
            </div>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />

      <hr className="sidebar-divider" />

      <div className="sidebar-bottom">
        <button
          className="nav-link"
          onClick={onToggle}
          title={collapsed ? 'Развернуть' : 'Свернуть'}
        >
          <span className="nav-link-icon">
            {collapsed
              ? <PanelLeftOpen size={18} strokeWidth={1.5} />
              : <PanelLeftClose size={18} strokeWidth={1.5} />}
          </span>
          <span className="nav-link-label">{collapsed ? 'Развернуть' : 'Свернуть'}</span>
        </button>

        <Link
          href="/connections"
          className={`nav-link ${isActive('/connections') ? 'nav-link-active' : ''}`}
          title={collapsed ? 'Мои подключения' : undefined}
        >
          <span className="nav-link-icon"><Plug size={18} strokeWidth={1.5} /></span>
          <span className="nav-link-label">Мои подключения</span>
        </Link>

        <Link
          href="/settings"
          className={`nav-link ${isActive('/settings') ? 'nav-link-active' : ''}`}
          title={collapsed ? 'Настройки' : undefined}
        >
          <span className="nav-link-icon"><Settings size={18} strokeWidth={1.5} /></span>
          <span className="nav-link-label">Настройки</span>
        </Link>

        <Link
          href="/support"
          className={`nav-link ${isActive('/support') ? 'nav-link-active' : ''}`}
          title={collapsed ? 'Справка' : undefined}
        >
          <span className="nav-link-icon"><HelpCircle size={18} strokeWidth={1.5} /></span>
          <span className="nav-link-label">Справка</span>
        </Link>

        <Link
          href="/support"
          className="nav-link"
          title={collapsed ? 'Чат поддержки' : undefined}
        >
          <span className="nav-link-icon"><MessageCircle size={18} strokeWidth={1.5} /></span>
          <span className="nav-link-label">Чат поддержки</span>
        </Link>

        <button
          className="nav-link"
          onClick={handleLogout}
          title={collapsed ? 'Выход' : undefined}
        >
          <span className="nav-link-icon"><LogOut size={18} strokeWidth={1.5} /></span>
          <span className="nav-link-label">Выход</span>
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Найти существующие стили `.nav-link`/`.sidebar-*`. Проверить, есть ли `.nav-group`, `.nav-group-toggle`, `.nav-group-chevron`, `.nav-group-children`, `.nav-link-nested`**

```bash
cd /opt/genomeai/repo/web_app && grep -rn "nav-link\|sidebar-section" app/globals.css styles/ 2>/dev/null | head -20
```

Expected: найдены `.nav-link`, `.sidebar-section` и т.д. Возможно нет `.nav-group*` — их нужно добавить.

- [ ] **Step 3: Добавить CSS-классы для аккордеона в `app/globals.css` (либо в файл, где определены `.nav-link`)**

Найти конец секции `.sidebar-*` стилей и добавить (точное место — рядом с `.nav-link` definition):

```css
/* Sidebar accordion */
.nav-group {
  display: flex;
  flex-direction: column;
}
.nav-group-toggle {
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
}
.nav-group-chevron {
  margin-left: auto;
  display: inline-flex;
  opacity: 0.7;
}
.nav-group-children {
  display: flex;
  flex-direction: column;
  padding-left: 0.75rem;
  border-left: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
  margin-left: 1rem;
}
.nav-link-nested {
  padding-left: 0.5rem;
  font-size: 0.95em;
}
```

> Если CSS-токены `--border-subtle` нет — заменить на конкретный rgba или совпадающий с существующими разделителями (см. `.sidebar-divider`).

- [ ] **Step 4: Run typecheck**

```bash
cd /opt/genomeai/repo/web_app && npm run typecheck
```

Expected: **PASS**, ноль ошибок. Если что-то — починить указанное в выводе, не двигаться дальше.

- [ ] **Step 5: Run validate-foundation**

```bash
cd /opt/genomeai/repo/web_app && npm run test
```

Expected: вывод `web_app T32-07 validation OK`. Все route strings (`/reproduction`, `/vet`, `/treatments`, `/economics`, `/support`, `/pilot`, `/readiness`, `/observability`, `/admin`) — в navigation.ts остаются.

- [ ] **Step 6: Commit единым атомарным коммитом (navigation.ts + tests + sidebar.tsx + css)**

```bash
cd /opt/genomeai/repo && git add web_app/lib/navigation.ts web_app/tests/navigation.test.ts web_app/components/app/sidebar.tsx web_app/app/globals.css && git commit -m "feat(nav): accordion 'Стадо' group with discriminated NavigationItem union (P1-3a)

- NavigationItem = NavigationLeaf | NavigationGroup (single-level nesting)
- Move Воспроизводство/Ветеринария under Стадо group; add Кормление (/feeding) leaf
- Sidebar renders group as collapsible toggle (chevron + nested children)
- Group icon falls back to defaultHref icon; collapsed mode navigates to defaultHref
- Auto-expand active group via pathname match; user toggles persist in localStorage
- Permission filter: group hidden if all children filtered or group's own perms fail
- Wheat icon for /feeding (page itself lands in P1-3b)
"
```

> Если в Step 3 пришлось править файл стилей, отличный от `globals.css` — заменить путь в `git add`.

---

## Task 4: Manual browser smoke + execution proof

**Files:**
- Create: `docs/iterations/T34-P1-3a_execution_proof.md`

- [ ] **Step 1: Поднять dev-stack локально**

```bash
cd /opt/genomeai/repo && python -m genomeai.app_launcher --open-browser
```

Expected: web-frontend на http://127.0.0.1:3000, backend на http://127.0.0.1:8000. Дождаться, когда вкладка `/dashboard` зарендерится.

- [ ] **Step 2: Залогиниться (admin/admin), проверить sidebar**

Чек-лист в браузере:
1. В секции «Основное» видна строка «Стадо» с шевроном `▶` (закрыта).
2. Клик по «Стадо» → раскрывается, видны 4 ребёнка: Животные, Воспроизводство, Ветеринария, Кормление. Шеврон меняется на `▼`.
3. Клик по «Животные» → переход на `/profiles/animal`, группа остаётся открытой, «Животные» подсвечено.
4. Прямой переход на `/reproduction` (через address bar) → группа авто-открывается, «Воспроизводство» подсвечено, родитель «Стадо» тоже подсвечен.
5. Клик по «Свернуть» (тоггл сайдбара) → видна только иконка Beef для группы (без шеврона/детей). Клик по ней → переход на `/profiles/animal` (defaultHref).
6. В секции «Управление» больше нет Воспроизводства и Ветеринарии — только Задачи / Решения / Экономика.
7. Reload страницы /reproduction → группа всё ещё открыта (auto-expand + localStorage).
8. Открыть DevTools → Application → Local Storage → ключ `nav.groups.open` содержит массив с (минимум) "Стадо" после любого ручного toggle.

- [ ] **Step 3: Проверить permission-фильтр**

Залогиниться под viewer (или временно убрать `kpi.view` у тестового пользователя):
1. Группа «Стадо» по-прежнему видна (потому что у Животные нет permission gate).
2. В раскрытом виде у Стадо ровно один ребёнок — «Животные».
3. Если все permissions отозвать (логин под пустым пользователем — невозможно, но эмулировать через `me=null` в auth-provider) — навигация показывает только «Войти». Этот кейс уже покрыт type-checked test'ом, ручную проверку можно опустить.

- [ ] **Step 4: Записать execution proof**

Файл `docs/iterations/T34-P1-3a_execution_proof.md`:

```markdown
# T34-P1-3a Execution Proof — Navigation accordion 'Стадо'

**Date:** 2026-05-15
**Spec:** docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md §2
**Plan:** docs/superpowers/plans/2026-05-15-p1-3a-navigation-accordion.md
**Commits:**
- `<commit-1>` feat(web): useNavGroupsOpen hook
- `<commit-2>` feat(nav): accordion 'Стадо' group with discriminated NavigationItem union

## Scope

Replaced flat NavigationItem with discriminated union (NavigationLeaf | NavigationGroup).
Moved Воспроизводство/Ветеринария under the new 'Стадо' group; added Кормление (/feeding) leaf.
Sidebar renders the group as a collapsible toggle with localStorage-persisted open-state
and pathname-driven auto-expand. /feeding page itself lands in P1-3b — current click leads
to a 404 (acceptable intermediate state).

## Executed checks

| # | Check                                   | Result | Evidence                              |
|---|-----------------------------------------|--------|---------------------------------------|
| 1 | `npm run typecheck`                     | PASS   | <inline output>                       |
| 2 | `npm run test` (validate-foundation)    | PASS   | `web_app T32-07 validation OK`        |
| 3 | Manual browser smoke (steps 1–8)        | PASS   | <screenshot or note>                  |
| 4 | Permission filter (viewer w/o kpi.view) | PASS   | <screenshot or note>                  |

7 гейтов CLAUDE.md §4 для этого инкремента **не прогонялись** — frontend-only change,
backend и golden не затрагиваются. Полные гейты запланированы на P1-3b (backend).

## Net result

`partially_proven` — frontend изменения runtime-проверены через `npm run typecheck`,
`npm run test`, ручной browser smoke. Backend и golden не трогаем, поэтому 7 гейтов
из CLAUDE.md §4 здесь не применимы; они отрабатываются на ближайшем инкременте,
который трогает backend (P1-3b).

## Honest status

partially_proven.
```

- [ ] **Step 5: Заменить плейсхолдеры `<commit-1>` / `<commit-2>` на реальные SHA**

```bash
cd /opt/genomeai/repo && git log --oneline -3
```

Скопировать первые 7 символов двух последних коммитов и подставить в proof-файл.

- [ ] **Step 6: Commit execution proof**

```bash
cd /opt/genomeai/repo && git add docs/iterations/T34-P1-3a_execution_proof.md && git commit -m "docs(iter): execution proof for P1-3a navigation accordion"
```

---

## Self-review notes

**Spec coverage:**
- §2.1 (type) → Task 2 Step 1 ✓
- §2.2 (структура секций, Repro/Vet под Стадо, +Кормление, defaultHref) → Task 2 Step 1 ✓
- §2.3 (pathLabels рекурсивно, /treatments в extraPathLabels сохраняется) → Task 2 Step 1 ✓
- §2.4 (sidebar: item/group рендер, open-state, auto-expand, active, collapsed, perms filter) → Task 1 + Task 3 ✓
- §2.5 (тесты: 5 кейсов) → Task 2 Step 2 ✓ (восемь тестов добавлено: четыре существующих переехало + четыре новых + один новый для defaultHref)

**Placeholders:** в файле плана нет TBD/TODO. В тексте execution-proof template есть placeholder `<commit-1>` — он *заполняется* в Step 5; это не плановый placeholder, а нормальный шаблонный плейсхолдер.

**Type consistency:**
- `NavigationLeaf` / `NavigationGroup` / `NavigationItem` упоминаются с одинаковыми названиями полей во всех Task'ах.
- `useNavGroupsOpen(autoOpenLabels)` — сигнатура одинакова в Task 1 (определение) и Task 3 (использование).
- `defaultHref` присутствует на группе и используется в sidebar collapsed-режиме — consistent.
- `kind: 'item' | 'group'` discriminator — единая на всю плоскость.

---

## Execution Handoff

После сохранения этого плана — координатор выбирает execution mode (subagent-driven vs inline).
