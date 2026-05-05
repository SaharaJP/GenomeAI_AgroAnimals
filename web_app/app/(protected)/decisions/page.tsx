'use client';

import { useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { Card } from '@/components/ui/card';
import { ResourceListPage } from '@/components/app/resource-list-page';

export default function DecisionsPage() {
  const searchParams = useSearchParams();

  const params = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [key, value] of searchParams.entries()) {
      out[key] = value;
    }
    return out;
  }, [searchParams]);

  const columns = useMemo(
    () => [
      {
        key: 'action',
        header: 'Action',
        render: (row: Record<string, unknown>) => String(row.action || '—'),
      },
      {
        key: 'username',
        header: 'User',
        render: (row: Record<string, unknown>) => String(row.username || '—'),
      },
      {
        key: 'created_at',
        header: 'Created at',
        render: (row: Record<string, unknown>) => String(row.created_at || '—'),
      },
    ],
    []
  );

  return (
    <div className="grid">
      {Object.keys(params).length > 0 ? (
        <Card>
          <h3 className="card-title">Decision hook context</h3>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
            {JSON.stringify(params, null, 2)}
          </pre>
        </Card>
      ) : null}

      <ResourceListPage<Record<string, unknown>>
        title="Решения"
        subtitle="Журнал решений с аудит-трейлом и привязкой к данным фермы."
        endpoint="/decisions"
        why={[
          'Семантика журнала решений не изменяется и полностью аудируема.',
          'Веб-оболочка читает канонический контрактный слой, общий с Android.',
        ]}
        columns={columns}
      />
    </div>
  );
}
