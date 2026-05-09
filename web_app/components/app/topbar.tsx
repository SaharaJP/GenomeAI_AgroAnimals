'use client';

import { usePathname, useRouter } from 'next/navigation';
import { LogOut, Leaf } from 'lucide-react';
import { useAuth } from '@/components/auth/auth-provider';
import { InsightNotificationBell } from '@/components/ai/insight-notification-bell';

const pathLabels: Record<string, string> = {
  '/daily-summary': 'Обзор',
  '/copilot':       'Помощник',
  '/worklists':     'Рабочие списки',
  '/reproduction':  'Воспроизводство',
  '/vet':           'Ветеринария',
  '/treatments':    'Лечение / каренция',
  '/decisions':     'Решения',
  '/economics':     'Экономика / сценарии',
  '/support':       'Поддержка',
  '/pilot':         'Пилот',
  '/readiness':     'Готовность системы',
  '/observability': 'Мониторинг',
  '/admin':         'Администрирование',
  '/admin/ai':      'AI-наблюдаемость',
  '/settings':      'Настройки',
  '/connections':   'Мои подключения',
};

function getPageLabel(pathname: string): string {
  if (pathLabels[pathname]) return pathLabels[pathname];
  // match prefix for nested routes
  const prefix = Object.keys(pathLabels).find((k) => pathname.startsWith(`${k}/`));
  return prefix ? pathLabels[prefix] : 'Страница';
}

function getInitials(username: string | undefined): string {
  if (!username) return 'ГА';
  const parts = username.split(/[\s._-]/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return username.slice(0, 2).toUpperCase();
}

export function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { me } = useAuth() as { me: any; loading: boolean };
  const pageLabel = getPageLabel(pathname);

  async function handleExitDemo() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.replace('/login');
    router.refresh();
  }

  return (
    <header className="topbar" role="banner">
      {/* Mobile: logo mark (hidden on desktop via CSS) */}
      <div className="topbar-mobile-logo" aria-hidden="true">
        <div className="topbar-mobile-logo-mark">
          <Leaf size={14} strokeWidth={2} color="white" />
        </div>
        <span>GenomeAI</span>
      </div>

      {/* Desktop: Breadcrumb (hidden on mobile via CSS) */}
      <nav className="topbar-breadcrumb" aria-label="Хлебные крошки">
        {me?.demo_mode && <span>Демо-ферма</span>}
        {me?.demo_mode && <span className="topbar-breadcrumb-sep">▸</span>}
        <span className="topbar-breadcrumb-current">{pageLabel}</span>
      </nav>

      {/* Right side */}
      <div className="topbar-right">
        <InsightNotificationBell />

        {me?.demo_mode && (
          <button className="topbar-btn-demo" onClick={handleExitDemo}>
            <LogOut size={13} strokeWidth={2} />
            <span>Выйти из демо-режима</span>
          </button>
        )}

        <div
          className="topbar-avatar"
          title={me?.user.username ?? 'Пользователь'}
          aria-label={`Аватар пользователя ${me?.user.username ?? ''}`}
        >
          {getInitials(me?.user.username)}
        </div>
      </div>
    </header>
  );
}
