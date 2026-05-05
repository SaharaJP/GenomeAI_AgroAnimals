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
  ListTodo,
  HeartPulse,
  Stethoscope,
  Scale,
  FlaskConical,
  TrendingUp,
  Users,
} from 'lucide-react';
import { useAuth } from '@/components/auth/auth-provider';
import { getNavigationSections } from '@/lib/navigation';

type Props = { collapsed: boolean; onToggle: () => void };

const navIconMap: Record<string, React.ReactNode> = {
  '/dashboard':          <Home size={18} strokeWidth={1.5} />,
  '/daily-summary':      <LayoutDashboard size={18} strokeWidth={1.5} />,
  '/insights':           <Lightbulb size={18} strokeWidth={1.5} />,
  '/analytics':          <BarChart2 size={18} strokeWidth={1.5} />,
  '/timeline':           <Clock size={18} strokeWidth={1.5} />,
  '/copilot':            <Bot size={18} strokeWidth={1.5} />,
  '/assistant':          <Bot size={18} strokeWidth={1.5} />,
  '/worklists':          <ListTodo size={18} strokeWidth={1.5} />,
  '/reproduction':       <HeartPulse size={18} strokeWidth={1.5} />,
  '/vet':                <Stethoscope size={18} strokeWidth={1.5} />,
  '/treatments':         <FlaskConical size={18} strokeWidth={1.5} />,
  '/decisions':          <Scale size={18} strokeWidth={1.5} />,
  '/economics':          <TrendingUp size={18} strokeWidth={1.5} />,
  '/profiles/animal':    <Users size={18} strokeWidth={1.5} />,
};

export function Sidebar({ collapsed, onToggle }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const { me } = useAuth() as { me: any; loading: boolean; refresh: () => Promise<void> };

  const sections = getNavigationSections(me);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.replace('/login');
    router.refresh();
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

      {/* All navigation sections — scrollable */}
      <div className="sidebar-sections">
        {sections.map((section, idx) => (
          <nav key={section.title} className={`sidebar-nav sidebar-nav--section${idx > 0 ? ' sidebar-nav--secondary' : ''}`} aria-label={section.title}>
            {!collapsed && sections.length > 1 && (
              <span className="sidebar-section-label">{section.title}</span>
            )}
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-link ${isActive(item.href) ? 'nav-link-active' : ''}`}
                title={collapsed ? item.label : undefined}
              >
                <span className="nav-link-icon">
                  {navIconMap[item.href] ?? <LayoutDashboard size={18} strokeWidth={1.5} />}
                </span>
                <span className="nav-link-label">{item.label}</span>
              </Link>
            ))}
          </nav>
        ))}
      </div>

      <hr className="sidebar-divider" />

      {/* Bottom utility nav */}
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
