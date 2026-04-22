'use client';

import { InsightStatus, INSIGHT_STATUS_LABELS } from '@/lib/api/insights';

type Props = {
  active: InsightStatus;
  counts: Record<InsightStatus, number>;
  onChange: (status: InsightStatus) => void;
};

const TABS: InsightStatus[] = ['to_check', 'to_follow_up', 'done'];

export function TriageTabs({ active, counts, onChange }: Props) {
  return (
    <div className="triage-tabs">
      {TABS.map((tab) => {
        const isActive = tab === active;
        const count = counts[tab];
        return (
          <button
            key={tab}
            className={`triage-tab-btn${isActive ? ' triage-tab-btn-active' : ''}`}
            onClick={() => onChange(tab)}
          >
            {INSIGHT_STATUS_LABELS[tab]}
            {count > 0 && (
              <span className="triage-tab-count">{count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
