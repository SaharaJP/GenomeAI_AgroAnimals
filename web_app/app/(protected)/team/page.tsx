'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { UserPlus } from 'lucide-react';
import { PersonnelSurface } from '@/components/team/personnel-surface';
import { PersonnelCreateModal } from '@/components/team/personnel-create-modal';
import { useAuth } from '@/components/auth/auth-provider';
import { hasPermission } from '@/lib/api/contracts';

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
  const { me } = useAuth();
  const canManagePersonnel = hasPermission(me, 'personnel.manage');
  const [personnelModalOpen, setPersonnelModalOpen] = useState(false);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);
  const [personnelReloadKey, setPersonnelReloadKey] = useState(0);

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
        <PersonnelSurface
          view={active}
          personnelReloadKey={personnelReloadKey}
        />
      </div>
      {createdNotice ? (
        <div className="task-create-toast" role="status" aria-live="polite">
          {createdNotice}
        </div>
      ) : null}
      {canManagePersonnel ? (
        <button
          type="button"
          className="team-add-fab"
          onClick={() => setPersonnelModalOpen(true)}
          aria-label="Добавить сотрудника"
        >
          <UserPlus size={18} aria-hidden="true" />
          <span>Добавить сотрудника</span>
        </button>
      ) : null}
      <PersonnelCreateModal
        open={personnelModalOpen}
        onClose={() => setPersonnelModalOpen(false)}
        onCreated={(person) => {
          setCreatedNotice(`Сотрудник создан: ${person.full_name}`);
          window.setTimeout(() => setCreatedNotice(null), 4000);
          setPersonnelReloadKey((n) => n + 1);
        }}
      />
    </>
  );
}
