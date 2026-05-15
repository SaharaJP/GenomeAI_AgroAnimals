'use client';

import { useEffect, useMemo, useState } from 'react';
import { EmptyState } from '@/components/ui/empty-state';
import { apiFetch } from '@/lib/api/client';
import type { Personnel, PersonnelListResponse } from '@/lib/api/contracts';
import { PersonnelDetail } from '@/components/team/personnel-detail';

type ViewMode = 'by-group' | 'by-name';

const NO_GROUP_KEY = '__no_group__';
const NO_GROUP_LABEL = 'Без группы';

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p.charAt(0).toUpperCase()).join('') || '?';
}

function groupByGroupId(items: Personnel[]): { key: string; label: string; rows: Personnel[] }[] {
  const buckets = new Map<string, Personnel[]>();
  for (const p of items) {
    const key = p.group_id || NO_GROUP_KEY;
    const list = buckets.get(key);
    if (list) {
      list.push(p);
    } else {
      buckets.set(key, [p]);
    }
  }
  return Array.from(buckets.entries())
    .map(([key, rows]) => ({
      key,
      label: key === NO_GROUP_KEY ? NO_GROUP_LABEL : key,
      rows: rows.slice().sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru')),
    }))
    .sort((a, b) => {
      if (a.key === NO_GROUP_KEY) return 1;
      if (b.key === NO_GROUP_KEY) return -1;
      return a.label.localeCompare(b.label, 'ru');
    });
}

function PersonnelCard({
  person,
  piiVisible,
  onOpen,
}: {
  person: Personnel;
  piiVisible: boolean;
  onOpen: (person: Personnel) => void;
}) {
  return (
    <article className="card personnel-card" aria-label={`Сотрудник: ${person.full_name}`}>
      <button
        type="button"
        className="personnel-card__open"
        onClick={() => onOpen(person)}
        aria-label={`Открыть карточку: ${person.full_name}`}
      >
        <div className="personnel-card__head">
          <div className="personnel-card__avatar" aria-hidden="true">
            {person.photo_ref ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={person.photo_ref} alt="" />
            ) : (
              <span className="personnel-card__initials">{initials(person.full_name)}</span>
            )}
          </div>
          <div className="personnel-card__title">
            <h3 className="card-title">{person.full_name}</h3>
            <p className="card-subtitle">{person.position}</p>
          </div>
        </div>
      </button>
      {piiVisible && (person.phone || person.email) ? (
        <dl className="personnel-card__contacts">
          {person.phone ? (
            <>
              <dt>Телефон</dt>
              <dd>
                <a href={`tel:${person.phone}`}>{person.phone}</a>
              </dd>
            </>
          ) : null}
          {person.email ? (
            <>
              <dt>Email</dt>
              <dd>
                <a href={`mailto:${person.email}`}>{person.email}</a>
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </article>
  );
}

export function PersonnelSurface({ view }: { view: ViewMode }) {
  const [data, setData] = useState<PersonnelListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Personnel | null>(null);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    void apiFetch<PersonnelListResponse>('/personnel')
      .then((res) => {
        if (active) setData(res);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Ошибка загрузки команды');
      });
    return () => {
      active = false;
    };
  }, []);

  const grouped = useMemo(() => {
    if (!data) return [];
    if (view === 'by-group') {
      return groupByGroupId(data.items);
    }
    return [
      {
        key: 'all',
        label: 'Все сотрудники',
        rows: data.items.slice().sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru')),
      },
    ];
  }, [data, view]);

  if (error) {
    return <EmptyState title="Не удалось загрузить команду" description={error} />;
  }
  if (data === null) {
    return <EmptyState title="Загрузка команды…" description="Запрашиваем список сотрудников." />;
  }
  if (data.total === 0) {
    return (
      <EmptyState
        title="Команда пока пуста"
        description="Добавьте сотрудника через POST /api/app/v1/personnel или модалку FAB (появится в P1-4d)."
      />
    );
  }

  return (
    <div className="personnel-surface" data-pii-visible={data.pii_visible ? 'true' : 'false'}>
      {!data.pii_visible ? (
        <p className="personnel-surface__hint" role="status">
          Контактные данные скрыты — у вашей роли нет права personnel.read_pii.
        </p>
      ) : null}
      {grouped.map((bucket) => (
        <section key={bucket.key} className="personnel-surface__bucket" aria-label={bucket.label}>
          <header className="personnel-surface__bucket-head">
            <h2>{bucket.label}</h2>
            <span className="personnel-surface__count">{bucket.rows.length}</span>
          </header>
          <div className="personnel-surface__grid">
            {bucket.rows.map((person) => (
              <PersonnelCard
                key={person.personnel_id}
                person={person}
                piiVisible={data.pii_visible}
                onOpen={setSelected}
              />
            ))}
          </div>
        </section>
      ))}
      {selected ? (
        <PersonnelDetail person={selected} piiVisible={data.pii_visible} onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}
