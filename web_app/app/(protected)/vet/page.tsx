'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { VetOverviewTab } from '@/components/vet/tabs/overview-tab';
import { VetWithdrawalTab } from '@/components/vet/tabs/withdrawal-tab';
import { VetTasksTab } from '@/components/vet/tabs/tasks-tab';

type VetTabId = 'overview' | 'withdrawal' | 'tasks';

const TABS: { id: VetTabId; label: string }[] = [
  { id: 'overview', label: 'Обзор' },
  { id: 'withdrawal', label: 'Каренция' },
  { id: 'tasks', label: 'Задачи' },
];

function isVetTabId(value: string | null): value is VetTabId {
  return value === 'overview' || value === 'withdrawal' || value === 'tasks';
}

export default function VetPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const active: VetTabId = useMemo(() => {
    const raw = searchParams.get('tab');
    return isVetTabId(raw) ? raw : 'overview';
  }, [searchParams]);

  const onSelect = (id: VetTabId) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('tab', id);
    router.replace(`/vet?${next.toString()}`, { scroll: false });
  };

  return (
    <>
      <div className="window-tabs" role="tablist" aria-label="Разделы ветеринарии">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`vet-tab-${tab.id}`}
            className={`window-tab${active === tab.id ? ' window-tab--active' : ''}`}
            role="tab"
            aria-selected={active === tab.id}
            aria-controls={`vet-tabpanel-${tab.id}`}
            onClick={() => onSelect(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`vet-tabpanel-${active}`} aria-labelledby={`vet-tab-${active}`}>
        {active === 'overview' && <VetOverviewTab />}
        {active === 'withdrawal' && <VetWithdrawalTab />}
        {active === 'tasks' && <VetTasksTab />}
      </div>
    </>
  );
}
