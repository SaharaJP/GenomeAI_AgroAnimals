import type { AuthMeResponse } from '@/lib/api/contracts';

export type NavigationItem = { label: string; href: string; minPermissions?: string[] };
export type NavigationSection = { title: string; items: NavigationItem[] };

const sections: NavigationSection[] = [
  {
    title: 'Daily operations',
    items: [
      { label: 'Home / Daily summary', href: '/daily-summary' },
      { label: 'Alerts', href: '/alerts', minPermissions: ['alerts.view', 'alerts.manage', 'alerts.read'] },
      { label: 'Worklists', href: '/worklists', minPermissions: ['tasks.view', 'tasks.read', 'tasks.manage'] },
      { label: 'Planner', href: '/planner', minPermissions: ['planner.view', 'planner.read'] },
      { label: 'Reproduction', href: '/reproduction', minPermissions: ['kpi.view'] },
      { label: 'Vet queues', href: '/vet', minPermissions: ['kpi.view'] },
      { label: 'Treatments / withdrawal', href: '/treatments', minPermissions: ['kpi.view'] },
      { label: 'Reports', href: '/reports', minPermissions: ['reports.view', 'reports.read', 'reports.approve'] },
      { label: 'Assistant', href: '/assistant', minPermissions: ['assistant.ask'] },
    ],
  },
  {
    title: 'Office / management',
    items: [
      { label: 'Decisions', href: '/decisions', minPermissions: ['decisionlog.view', 'decisions.read'] },
      { label: 'Economics / what-if', href: '/economics', minPermissions: ['economics.read', 'whatif.scenarios.view'] },
      { label: 'Support', href: '/support', minPermissions: ['support.read', 'jobs.view', 'audit.view'] },
      { label: 'Pilot', href: '/pilot', minPermissions: ['support.read', 'jobs.view'] },
      { label: 'Readiness', href: '/readiness', minPermissions: ['support.read', 'audit.view'] },
      { label: 'Observability', href: '/observability', minPermissions: ['audit.view', 'jobs.view'] },
      { label: 'Admin', href: '/admin', minPermissions: ['audit.view'] },
    ],
  },
];

export function getNavigationSections(me: AuthMeResponse | null): NavigationSection[] {
  const permissions = new Set(me?.user.permissions || []);
  if (!me) return [{ title: 'General', items: [{ label: 'Login', href: '/login' }] }];
  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !item.minPermissions || item.minPermissions.some((permission) => permissions.has(permission))),
    }))
    .filter((section) => section.items.length > 0);
}
