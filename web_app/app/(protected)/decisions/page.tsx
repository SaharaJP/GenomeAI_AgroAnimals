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
        title="Decisions"
        subtitle="Decision intelligence foundation against canonical backend API contracts."
        endpoint="/decisions"
        why={[
          'Decision log semantics stay unchanged and auditable.',
          'The web shell reads a canonical contract layer shared with Android.',
        ]}
        columns={columns}
      />
    </div>
  );
}
