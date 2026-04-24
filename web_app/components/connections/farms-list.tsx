'use client';

import { useEffect, useState } from 'react';

type Farm = { id: string; name: string; status: string };

export function FarmsList() {
  const [farms, setFarms] = useState<Farm[]>([]);
  const [toast, setToast] = useState(false);

  useEffect(() => {
    fetch('/api/connections')
      .then((r) => r.json())
      .then((d) => setFarms(d.farms ?? []))
      .catch(() => setFarms([{ id: 'demo-farm', name: 'Демо-ферма', status: 'Sandbox' }]));
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
        <button className="btn-outline-teal" onClick={handleConnect}>
          + Подключить новую ферму
        </button>
      </div>

      <div className="triage-tabs" style={{ marginBottom: 16 }}>
        <button className="triage-tab-btn triage-tab-btn-active">Farms</button>
      </div>

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

      {toast && (
        <div className="toast" role="status">
          Функция в разработке. Свяжитесь с саппортом чтобы подключить ферму.
        </div>
      )}
    </>
  );
}
