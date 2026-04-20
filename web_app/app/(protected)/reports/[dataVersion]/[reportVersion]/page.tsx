import { ReportViewSurface } from '@/components/reports/report-view-surface';

export default async function ReportDetailPage({ params }: { params: Promise<{ dataVersion: string; reportVersion: string }> }) {
  const { dataVersion, reportVersion } = await params;
  return <ReportViewSurface dataVersion={dataVersion} reportVersion={reportVersion} />;
}
