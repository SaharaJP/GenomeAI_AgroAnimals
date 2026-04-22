import { TrendingUp } from 'lucide-react';
import { InfoBanner } from '@/components/overview/info-banner';
import { HeroGreeting } from '@/components/overview/hero-greeting';
import { AttentionCard } from '@/components/overview/attention-card';
import { InsightsColumn } from '@/components/overview/insights-column';
import { TimelineColumn } from '@/components/overview/timeline-column';
import { DataColumn } from '@/components/overview/data-column';

export default function DashboardPage() {
  return (
    <div>
      <InfoBanner />
      <HeroGreeting />

      <AttentionCard />

      <div className="overview-section-heading">
        <TrendingUp size={17} color="var(--text-secondary)" />
        <span>Последние события на вашей ферме</span>
      </div>

      <div className="overview-columns">
        <InsightsColumn />
        <TimelineColumn />
        <DataColumn />
      </div>
    </div>
  );
}
