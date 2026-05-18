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
      { kind: 'item', label: 'Команда', href: '/team', minPermissions: ['personnel.read'] },
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
  '/admin/ai': 'AI-наблюдаемость',
  '/admin/iam': 'IAM-матрица',
  '/admin/integrations': 'Контроль интеграций',
  '/admin/logs': 'Логи системы',
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
