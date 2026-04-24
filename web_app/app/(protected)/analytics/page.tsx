import dynamic from 'next/dynamic';

// Analytics charts are heavy — lazy-load to keep initial bundle small
const AnalyticsTabs = dynamic(
  () => import('@/components/analytics/analytics-tabs').then((m) => m.AnalyticsTabs),
  {
    loading: () => (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Загружаю графики…
      </div>
    ),
    ssr: false,
  },
);

export default function AnalyticsPage() {
  return (
    <div>
      <h1 className="page-title">Аналитика</h1>
      <p className="page-subtitle" style={{ marginBottom: 20 }}>
        Визуализируйте данные вашей фермы для выявления трендов и возможностей
      </p>
      <AnalyticsTabs />
    </div>
  );
}
