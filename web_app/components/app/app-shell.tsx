'use client';

import { useState } from 'react';
import { Sidebar } from './sidebar';
import { Topbar } from './topbar';
import { FAB } from './fab';
import { MobileTabBar } from './mobile-tab-bar';

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={`shell ${collapsed ? 'shell-collapsed' : ''}`}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />

      <div className="shell-body">
        <Topbar />
        <main className="shell-content">
          {children}
        </main>
      </div>

      <FAB />
      <MobileTabBar />
    </div>
  );
}
