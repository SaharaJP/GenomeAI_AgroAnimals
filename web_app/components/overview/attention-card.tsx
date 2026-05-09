'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { apiFetch } from '@/lib/api/client';
import { type AlertItem, type ListResponse } from '@/lib/api/contracts';

export function AttentionCard() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<ListResponse<AlertItem>>('/alerts?limit=5')
      .then(data => {
        const urgent = (data.items ?? []).filter(
          a => a.severity === 'urgent' || a.severity === 'high'
        );
        setAlerts(urgent.slice(0, 3));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="attention-section">
      <div className="attention-pill">⚠ Требует вашего внимания</div>
      <div className="card" style={{ padding: '14px 18px' }}>
        {loading ? (
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</span>
        ) : alerts.length > 0 ? (
          <div style={{ display: 'grid', gap: 10 }}>
            {alerts.map(alert => (
              <div key={alert.alert_id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <span style={{ fontSize: 15, marginTop: 1 }}>⚠</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                    {alert.title}
                  </div>
                  {alert.entity?.label && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                      {alert.entity.label}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <Link
              href="/insights"
              style={{ fontSize: 12, color: 'var(--accent-text)', fontWeight: 500, marginTop: 4 }}
            >
              Просмотреть все предупреждения →
            </Link>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20 }}>👍</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Всё под контролем. Ничего срочного.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
