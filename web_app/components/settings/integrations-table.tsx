'use client';

import { useEffect, useState } from 'react';

type Integration = {
  id: string;
  system: string;
  dataTypes: string;
  lastUpdated: string;
};

export function IntegrationsTable() {
  const [items, setItems] = useState<Integration[]>([]);

  useEffect(() => {
    fetch('/api/integrations')
      .then((r) => r.json())
      .then((d) => setItems(d.integrations ?? []))
      .catch(() =>
        setItems([
          { id: 'bovSync', system: 'BoviSync', dataTypes: 'Данные коров, Доильная система, Тест молока', lastUpdated: 'Суббота, 21 марта 2026, 01:02' },
          { id: 'datamars', system: 'Datamars Livestock Active Tag', dataTypes: 'Поведение', lastUpdated: 'Суббота, 21 марта 2026, 12:04' },
          { id: 'dfa', system: 'DFA', dataTypes: 'Вывоз молока', lastUpdated: 'Суббота, 21 марта 2026, 13:00' },
        ])
      );
  }, []);

  return (
    <section className="settings-section">
      <h2 className="settings-section-title">Подключённые источники данных</h2>
      <p className="settings-section-subtitle">
        Данные реального времени из внешних систем, подключённых к нашей платформе.{' '}
        Легко отслеживайте последние импорты, чтобы инсайты всегда были актуальны.
      </p>
      <div className="settings-card">
        <table className="settings-integrations-table">
          <thead>
            <tr>
              <th>Система</th>
              <th>Тип данных</th>
              <th>Последнее обновление</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td style={{ fontWeight: 500 }}>{row.system}</td>
                <td style={{ color: 'var(--text-secondary)' }}>{row.dataTypes}</td>
                <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{row.lastUpdated}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
