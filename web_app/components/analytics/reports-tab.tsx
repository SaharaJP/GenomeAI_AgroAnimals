'use client';

import { useSearchParams } from 'next/navigation';
import { ReportCatalogSurface } from '@/components/analytics/reports/report-catalog-surface';
import { ReportViewSurface } from '@/components/analytics/reports/report-view-surface';

export function ReportsTab() {
  const sp = useSearchParams();
  const dataVersion = sp.get('data_version');
  const reportVersion = sp.get('report_version');

  if (dataVersion && reportVersion) {
    return <ReportViewSurface dataVersion={dataVersion} reportVersion={reportVersion} />;
  }
  return <ReportCatalogSurface />;
}
