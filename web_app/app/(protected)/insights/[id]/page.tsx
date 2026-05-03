'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { DEMO_INSIGHTS, InsightStatus } from '@/lib/api/insights';
import { InsightDetail } from '@/components/insights/insight-detail';

export default function InsightDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const insight = DEMO_INSIGHTS.find((i) => i.insight_id === id);
  const [status, setStatus] = useState<InsightStatus>(insight?.status ?? 'to_check');

  if (!insight) {
    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Link
            href="/insights"
            style={{
              fontSize: 13,
              color: 'var(--accent-text)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <ArrowLeft size={13} /> Инсайты
          </Link>
        </div>
        <h1 className="page-title">Инсайт не найден</h1>
        <p className="page-subtitle">Инсайт {id} не существует или был удалён.</p>
      </div>
    );
  }

  return (
    <InsightDetail insight={insight} status={status} onStatusChange={setStatus} />
  );
}
