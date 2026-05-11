import type { AuthMeResponse } from '@/lib/api/contracts';

export type NavigationItem = { label: string; href: string; minPermissions?: string[] };
export type NavigationSection = { title: string; items: NavigationItem[] };

const sections: NavigationSection[] = [
  {
    title: 'Основное',
    items: [
      { label: 'Главная', href: '/dashboard' },
      { label: 'Брифинг', href: '/daily-summary' },
      { label: 'Инсайты', href: '/insights', minPermissions: ['alerts.view', 'alerts.manage', 'alerts.read'] },
      { label: 'Аналитика', href: '/analytics', minPermissions: ['reports.view', 'reports.read', 'reports.approve'] },
      { label: 'Лента событий', href: '/timeline' },
      { label: 'Стадо', href: '/profiles/animal' },
      { label: 'Помощник', href: '/copilot', minPermissions: ['assistant.ask'] },
    ],
  },
  {
    title: 'Управление',
    items: [
      { label: 'Задачи', href: '/worklists', minPermissions: ['tasks.view', 'tasks.read', 'tasks.manage'] },
      { label: 'Воспроизводство', href: '/reproduction', minPermissions: ['kpi.view'] },
      { label: 'Ветеринария', href: '/vet', minPermissions: ['kpi.view'] },
      { label: 'Решения', href: '/decisions', minPermissions: ['decisionlog.view', 'decisions.read'] },
      { label: 'Экономика', href: '/economics', minPermissions: ['economics.read', 'whatif.scenarios.view'] },
    ],
  },
  {
    title: 'Сервисы',
    items: [
      { label: 'Поддержка', href: '/support', minPermissions: ['support.read', 'jobs.view', 'audit.view'] },
      { label: 'Пилот', href: '/pilot', minPermissions: ['support.read', 'jobs.view'] },
      { label: 'Готовность системы', href: '/readiness', minPermissions: ['support.read', 'audit.view'] },
      { label: 'Мониторинг', href: '/observability', minPermissions: ['audit.view', 'jobs.view'] },
      { label: 'Администрирование', href: '/admin', minPermissions: ['audit.view'] },
    ],
  },
];

const extraPathLabels: Record<string, string> = {
  '/treatments': 'Лечение',
  '/admin/ai': 'AI-наблюдаемость',
  '/settings': 'Настройки',
  '/connections': 'Мои подключения',
};

export const pathLabels: Record<string, string> = (() => {
  const out: Record<string, string> = { ...extraPathLabels };
  for (const section of sections) {
    for (const item of section.items) {
      out[item.href] = item.label;
    }
  }
  return out;
})();

export function getNavigationSections(me: AuthMeResponse | null): NavigationSection[] {
  const permissions = new Set(me?.user.permissions || []);
  if (!me) return [{ title: 'Общее', items: [{ label: 'Войти', href: '/login' }] }];
  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter(
        (item) => !item.minPermissions || item.minPermissions.some((p) => permissions.has(p)),
      ),
    }))
    .filter((section) => section.items.length > 0);
}
