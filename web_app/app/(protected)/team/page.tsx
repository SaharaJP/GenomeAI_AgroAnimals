'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { EmptyState } from '@/components/ui/empty-state';

type TeamTabId = 'by-group' | 'by-name';

const TABS: { id: TeamTabId; label: string }[] = [
  { id: 'by-group', label: 'По группам' },
  { id: 'by-name', label: 'По ФИО' },
];

function isTeamTabId(value: string | null): value is TeamTabId {
  return value === 'by-group' || value === 'by-name';
}

export default function TeamPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const active: TeamTabId = useMemo(() => {
    const raw = searchParams.get('view');
    return isTeamTabId(raw) ? raw : 'by-group';
  }, [searchParams]);

  const onSelect = (id: TeamTabId) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('view', id);
    router.replace(`/team?${next.toString()}`, { scroll: false });
  };

  return (
    <>
      <div className="window-tabs" role="tablist" aria-label="Разделы команды">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`team-tab-${tab.id}`}
            className={`window-tab${active === tab.id ? ' window-tab--active' : ''}`}
            role="tab"
            aria-selected={active === tab.id}
            aria-controls={`team-tabpanel-${tab.id}`}
            onClick={() => onSelect(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`team-tabpanel-${active}`} aria-labelledby={`team-tab-${active}`}>
        <EmptyState
          title={active === 'by-group' ? 'Группы пока не отображаются' : 'Список сотрудников пока не загружен'}
          description="Данные подключим в P1-4b-2: список будет браться из GET /api/app/v1/personnel и группироваться по выбранному режиму."
        />
      </div>
    </>
  );
}
