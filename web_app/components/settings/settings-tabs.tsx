'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/components/auth/auth-provider';
import { AccountDetails } from './account-details';
import { NotificationsTable } from './notifications-table';
import { IntegrationsTable } from './integrations-table';

type Tab = 'general' | 'farm-inputs';

type Settings = {
  notifications: { kpiInsightsEmail: boolean };
  weeklyBriefing: boolean;
};

const fallback: Settings = {
  notifications: { kpiInsightsEmail: true },
  weeklyBriefing: true,
};

export function SettingsTabs() {
  const [tab, setTab] = useState<Tab>('general');
  const [settings, setSettings] = useState<Settings>(fallback);
  const { me } = useAuth() as { me: any };

  useEffect(() => {
    fetch('/api/user/settings')
      .then((r) => r.json())
      .then(setSettings)
      .catch(() => {});
  }, []);

  async function patch(next: Settings) {
    setSettings(next);
    await fetch('/api/user/settings', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(next),
    });
  }

  return (
    <div>
      <div className="triage-tabs" style={{ marginBottom: 24 }}>
        <button
          className={`triage-tab-btn${tab === 'general' ? ' triage-tab-btn-active' : ''}`}
          onClick={() => setTab('general')}
        >
          Общее
        </button>
        <button
          className={`triage-tab-btn${tab === 'farm-inputs' ? ' triage-tab-btn-active' : ''}`}
          onClick={() => setTab('farm-inputs')}
        >
          Входные данные фермы
        </button>
      </div>

      {tab === 'general' && (
        <>
          <AccountDetails
            displayName={me?.user?.username ?? 'Андрей Жиров'}
            email="icreem714@gmail.com"
          />
          <NotificationsTable
            kpiInsightsEmail={settings.notifications.kpiInsightsEmail}
            weeklyBriefing={settings.weeklyBriefing}
            onKpiChange={(v) =>
              patch({ ...settings, notifications: { kpiInsightsEmail: v } })
            }
            onBriefingChange={(v) => patch({ ...settings, weeklyBriefing: v })}
          />
          <IntegrationsTable />
        </>
      )}

      {tab === 'farm-inputs' && (
        <div className="an-soon">
          <div className="settings-soon-pictogram" aria-hidden="true">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
              <rect x="8" y="22" width="48" height="34" rx="4" stroke="currentColor" strokeWidth="2" />
              <path d="M22 22V16a10 10 0 0120 0v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="32" cy="38" r="4" stroke="currentColor" strokeWidth="2" />
              <line x1="32" y1="42" x2="32" y2="46" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>Скоро</div>
          <div style={{ fontSize: 13 }}>Настройка входных данных фермы появится в следующих версиях</div>
        </div>
      )}
    </div>
  );
}
