'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Plus, UserPlus } from 'lucide-react';
import { PersonnelSurface } from '@/components/team/personnel-surface';
import { PersonnelCreateModal } from '@/components/team/personnel-create-modal';
import { TaskCreateModal } from '@/components/team/task-create-modal';
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
  const canCreateTasks = hasPermission(me, 'tasks.write');
  const canManagePersonnel = hasPermission(me, 'personnel.manage');
  const [modalOpen, setModalOpen] = useState(false);
  const [personnelModalOpen, setPersonnelModalOpen] = useState(false);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);
  const [worklistsReloadKey, setWorklistsReloadKey] = useState(0);
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
          worklistsReloadKey={worklistsReloadKey}
          personnelReloadKey={personnelReloadKey}
        />
      </div>
      {createdNotice ? (
        <div className="task-create-toast" role="status" aria-live="polite">
          {createdNotice}
        </div>
      ) : null}
      <div className="team-fab-stack">
        {canManagePersonnel ? (
          <button
            type="button"
            className="task-create-fab task-create-fab--secondary"
            onClick={() => setPersonnelModalOpen(true)}
            aria-label="Добавить сотрудника"
          >
            <UserPlus size={18} aria-hidden="true" />
            <span>Добавить сотрудника</span>
          </button>
        ) : null}
        {canCreateTasks ? (
          <button
            type="button"
            className="task-create-fab"
            onClick={() => setModalOpen(true)}
            aria-label="Поставить задачу"
          >
            <Plus size={18} aria-hidden="true" />
            <span>Поставить задачу</span>
          </button>
        ) : null}
      </div>
      <TaskCreateModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={(resp) => {
          setCreatedNotice(`Задача создана: ${resp.item.title}`);
          window.setTimeout(() => setCreatedNotice(null), 4000);
          setWorklistsReloadKey((n) => n + 1);
        }}
      />
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
