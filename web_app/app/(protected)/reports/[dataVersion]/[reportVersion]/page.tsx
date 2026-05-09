import { redirect } from 'next/navigation';

export default async function ReportsViewRedirect({
  params,
}: {
  params: Promise<{ dataVersion: string; reportVersion: string }>;
}) {
  const { dataVersion, reportVersion } = await params;
  redirect(
    `/analytics?tab=reports&data_version=${encodeURIComponent(dataVersion)}&report_version=${encodeURIComponent(reportVersion)}`,
  );
}
