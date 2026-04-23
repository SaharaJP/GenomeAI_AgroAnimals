'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Lightbulb, BarChart2, Clock, Menu } from 'lucide-react';

const tabs = [
  { label: 'Обзор',    href: '/daily-summary', icon: <LayoutDashboard size={20} strokeWidth={1.5} /> },
  { label: 'Инсайты',  href: '/alerts',        icon: <Lightbulb size={20} strokeWidth={1.5} /> },
  { label: 'Аналитика',href: '/reports',       icon: <BarChart2 size={20} strokeWidth={1.5} /> },
  { label: 'Лента',    href: '/timeline',      icon: <Clock size={20} strokeWidth={1.5} /> },
  { label: 'Меню',     href: '/daily-summary', icon: <Menu size={20} strokeWidth={1.5} /> },
] as const;

export function MobileTabBar() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav className="mobile-tab-bar" aria-label="Мобильная навигация">
      <div className="mobile-tab-bar-inner">
        {tabs.map((tab) => (
          <Link
            key={`${tab.href}-${tab.label}`}
            href={tab.href}
            className={`mobile-tab ${isActive(tab.href) && tab.label !== 'Меню' ? 'mobile-tab-active' : ''}`}
            aria-label={tab.label}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </Link>
        ))}
      </div>
    </nav>
  );
}
