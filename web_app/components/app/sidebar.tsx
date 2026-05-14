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

  const isGroupActive = (group: NavigationGroup) =>
    group.items.some((c) => isActive(c.href));

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
    const childrenId = `nav-group-${encodeURIComponent(group.label)}`;

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
          aria-controls={childrenId}
        >
          <span className="nav-link-icon">{groupIcon(group.defaultHref)}</span>
          <span className="nav-link-label">{group.label}</span>
          <span className="nav-group-chevron">
            {open ? <ChevronDown size={16} strokeWidth={1.5} /> : <ChevronRight size={16} strokeWidth={1.5} />}
          </span>
        </button>
        {open && (
          <div id={childrenId} className="nav-group-children" role="group" aria-label={group.label}>
            {group.items.map((c) => renderLeaf(c, { nested: true }))}
          </div>
        )}
      </div>
    );
  }

  return (
    <aside className="sidebar">
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
