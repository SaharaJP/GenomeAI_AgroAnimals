import { MorningBriefCard } from '@/components/overview/morning-brief-card';
import { DailyOperationsDashboard } from '@/components/operations/daily-operations-dashboard';

export default function DailySummaryPage() {
  return (
    <>
      <MorningBriefCard />
      <DailyOperationsDashboard />
    </>
  );
}
