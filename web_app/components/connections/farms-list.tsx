'use client';

import { useEffect, useState } from 'react';
import { Link2, Plus, Server } from 'lucide-react';
import Link from 'next/link';

type Farm = { id: string; name: string; status: string };

function FarmsTableSkeleton() {
  return (
    <div className="settings-card">
      {[1, 2, 3].map((i) => (
        <div key={i} className="skeleton-row">
          <div className="skeleton-avatar skeleton" />
          <div className="skeleton-lines">
            <div className="skeleton skeleton-text" style={{ width: '60%' }} />
            <div className="skeleton skeleton-text skeleton-text--sm" style={{ width: '35%' }} />
          </div>
          <div className="skeleton skeleton-text" style={{ width: 64, height: 22, borderRadius: 999 }} />
        </div>
      ))}
    </div>
  );
}

function EmptyFarmsState({ onConnect }: { onConnect: () => void }) {
  return (
    <div className="settings-card">
      <div className="empty-illustration">
        <div className="empty-illustration-icon">
          <Server size={24} />
        </div>
        <div className="empty-illustration-title">Нет подключённых ферм</div>
        <div className="empty-illustration-desc">
          Подключите первую ферму, чтобы начать получать данные о надоях, воспроизводстве и состоянии стада в реальном времени.
        </div>
        <Link href="/connections/import">
          <button className="button button-primary" type="button">
            <Plus size={14} />
            Подключить ферму
          </button>
        </Link>
      </div>
    </div>
  );
}

export function FarmsList() {
  const [farms, setFarms] = useState<Farm[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(false);

  useEffect(() => {
    fetch('/api/connections')
      .then((r) => r.json())
      .then((d) => {
        setFarms(d.farms ?? []);
        setLoading(false);
      })
      .catch(() => {
        setFarms([{ id: 'demo-farm', name: 'Демо-ферма', status: 'Sandbox' }]);
        setLoading(false);
      });
  }, []);

  function handleConnect() {
    setToast(true);
    setTimeout(() => setToast(false), 4000);
  }

  return (
    <>
      <div className="connections-header">
        <div>
          <h1 className="page-title">Подключённые фермы</h1>
          <p className="page-subtitle">Фермы, к которым у вас есть доступ</p>
        </div>
        <Link href="/connections/import">
          <button className="btn-outline-teal" type="button">
            <Link2 size={14} />
            Подключить новую ферму
          </button>
        </Link>
      </div>

      <div className="triage-tabs" style={{ marginBottom: 16 }}>
        <button className="triage-tab-btn triage-tab-btn-active" type="button">Farms</button>
      </div>

      {loading ? (
        <FarmsTableSkeleton />
      ) : farms.length === 0 ? (
        <EmptyFarmsState onConnect={handleConnect} />
      ) : (
        <div className="settings-card">
          <table className="settings-integrations-table">
            <thead>
              <tr>
                <th>Название фермы</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {farms.map((f) => (
                <tr key={f.id}>
                  <td style={{ fontWeight: 500 }}>{f.name}</td>
                  <td><span className="badge">{f.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          Функция в разработке. Свяжитесь с саппортом чтобы подключить ферму.
        </div>
      )}
    </>
  );
}
