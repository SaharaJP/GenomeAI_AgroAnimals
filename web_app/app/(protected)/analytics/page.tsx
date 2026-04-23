import { AnalyticsTabs } from '@/components/analytics/analytics-tabs';

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
