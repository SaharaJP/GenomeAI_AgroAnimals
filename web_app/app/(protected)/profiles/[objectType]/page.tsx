'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { use } from 'react';
import Link from 'next/link';
import { Search, ChevronRight, Filter, X } from 'lucide-react';

type Animal = {
  animal_id: string;
  breed: string;
  status: string;
  pen_id: string;
};

type FilterOptions = {
  breeds: string[];
  statuses: string[];
  pen_ids: string[];
};

type ColumnFilters = {
  breed: string;
  status: string;
  pen_id: string;
};

type PageParams = { objectType: string };

export default function ObjectTypeListPage({ params }: { params: Promise<PageParams> }) {
  const { objectType } = use(params);

  if (objectType !== 'animal') {
    return (
      <div className="empty-state" style={{ padding: '48px 0' }}>
        <p>Список «{objectType}» недоступен.</p>
      </div>
    );
  }

  return <AnimalListPage />;
}

function ColumnFilterPopover({
  column,
  options,
  value,
  onChange,
  onClose,
}: {
  column: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  onClose: () => void;
}) {
  const [localSearch, setLocalSearch] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  const filtered = options.filter((o) =>
    o.toLowerCase().includes(localSearch.toLowerCase())
  );

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        top: '100%',
        left: 0,
        zIndex: 100,
        background: 'var(--surface, #fff)',
        border: '1px solid var(--border, #e2e8f0)',
        borderRadius: 8,
        boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
        minWidth: 200,
        padding: '10px 0 6px',
      }}
    >
      <div style={{ padding: '0 10px 8px' }}>
        <div style={{ position: 'relative' }}>
          <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            autoFocus
            className="input"
            placeholder="Поиск..."
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            style={{ paddingLeft: 26, fontSize: 12, height: 28, width: '100%' }}
          />
        </div>
      </div>

      {value && (
        <button
          onClick={() => { onChange(''); onClose(); }}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            width: '100%', padding: '4px 12px', background: 'none', border: 'none',
            cursor: 'pointer', fontSize: 12, color: 'var(--teal)',
          }}
        >
          <X size={11} /> Сбросить фильтр
        </button>
      )}

      <div style={{ maxHeight: 180, overflowY: 'auto' }}>
        {filtered.length === 0 ? (
          <div style={{ padding: '6px 12px', fontSize: 12, color: 'var(--text-muted)' }}>Нет вариантов</div>
        ) : (
          filtered.map((opt) => (
            <button
              key={opt}
              onClick={() => { onChange(opt); onClose(); }}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '5px 12px', background: value === opt ? 'var(--teal-light, #e6f7f5)' : 'none',
                border: 'none', cursor: 'pointer', fontSize: 13,
                color: value === opt ? 'var(--teal)' : 'var(--text)',
                fontWeight: value === opt ? 600 : 400,
              }}
            >
              {opt}
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function FilterableHeader({
  label,
  filterKey,
  options,
  value,
  onChange,
}: {
  label: string;
  filterKey: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const active = !!value;

  return (
    <th style={{ position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {label}
        <button
          onClick={() => setOpen((o) => !o)}
          title={active ? `Фильтр: ${value}` : 'Фильтр'}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 2,
            color: active ? 'var(--teal)' : 'var(--text-muted)',
            display: 'inline-flex', alignItems: 'center',
          }}
        >
          <Filter size={12} strokeWidth={active ? 2.5 : 1.5} />
        </button>
        {active && (
          <span style={{
            fontSize: 10, background: 'var(--teal)', color: '#fff',
            borderRadius: 10, padding: '1px 6px', maxWidth: 80,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {value}
          </span>
        )}
      </div>
      {open && (
        <ColumnFilterPopover
          column={filterKey}
          options={options}
          value={value}
          onChange={onChange}
          onClose={() => setOpen(false)}
        />
      )}
    </th>
  );
}

function AnimalListPage() {
  const [animals, setAnimals] = useState<Animal[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState<ColumnFilters>({ breed: '', status: '', pen_id: '' });
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({ breeds: [], statuses: [], pen_ids: [] });
  const PAGE_SIZE = 50;

  useEffect(() => {
    fetch('/api/backend/api/app/v1/animals/filter-options', { cache: 'no-store' })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d) setFilterOptions(d); })
      .catch(() => {});
  }, []);

  const fetchAnimals = useCallback(async (q: string, pageNum: number, f: ColumnFilters) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(pageNum * PAGE_SIZE),
      });
      if (q) params.set('search', q);
      if (f.breed) params.set('breed', f.breed);
      if (f.status) params.set('status', f.status);
      if (f.pen_id) params.set('pen_id', f.pen_id);
      const res = await fetch(`/api/backend/api/app/v1/animals?${params}`, { cache: 'no-store' });
      if (!res.ok) throw new Error('bad status');
      const data = await res.json();
      setAnimals(data.animals ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setAnimals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => { setPage(0); fetchAnimals(search, 0, filters); }, 300);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, filters]);

  useEffect(() => {
    fetchAnimals(search, page, filters);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const setFilter = (key: keyof ColumnFilters) => (value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(0);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const hasActiveFilters = filters.breed || filters.status || filters.pen_id;

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div>
          <h1 className="page-title">Животные</h1>
          <p className="page-subtitle">Все животные на ферме ({total} голов)</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {hasActiveFilters && (
            <button
              className="btn-outline"
              onClick={() => setFilters({ breed: '', status: '', pen_id: '' })}
              style={{ fontSize: 12, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <X size={12} /> Сбросить фильтры
            </button>
          )}
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              className="input"
              placeholder="Поиск по ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ paddingLeft: 32, width: 220 }}
            />
          </div>
        </div>
      </div>

      <div className="settings-card">
        {loading ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>Загрузка...</div>
        ) : animals.length === 0 ? (
          <div className="empty-state" style={{ padding: '32px 0' }}>Животные не найдены</div>
        ) : (
          <table className="settings-integrations-table">
            <thead>
              <tr>
                <th>ID животного</th>
                <FilterableHeader
                  label="Порода"
                  filterKey="breed"
                  options={filterOptions.breeds}
                  value={filters.breed}
                  onChange={setFilter('breed')}
                />
                <FilterableHeader
                  label="Статус"
                  filterKey="status"
                  options={filterOptions.statuses}
                  value={filters.status}
                  onChange={setFilter('status')}
                />
                <FilterableHeader
                  label="Группа / Пен"
                  filterKey="pen_id"
                  options={filterOptions.pen_ids}
                  value={filters.pen_id}
                  onChange={setFilter('pen_id')}
                />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {animals.map((a) => (
                <tr key={a.animal_id}>
                  <td style={{ fontWeight: 600 }}>{a.animal_id}</td>
                  <td>{a.breed}</td>
                  <td>
                    <span className={`badge${a.status === 'active' ? ' badge-success' : ''}`}>
                      {a.status === 'active' ? 'Активна' : a.status}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>{a.pen_id}</td>
                  <td style={{ textAlign: 'right' }}>
                    <Link href={`/profiles/animal/${a.animal_id}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--teal)', fontSize: 13 }}>
                      Профиль <ChevronRight size={13} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
          <button
            className="btn-outline"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            style={{ fontSize: 13, padding: '5px 14px' }}
          >
            ← Назад
          </button>
          <span style={{ lineHeight: '30px', fontSize: 13, color: 'var(--text-muted)' }}>
            {page + 1} / {totalPages}
          </span>
          <button
            className="btn-outline"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
            style={{ fontSize: 13, padding: '5px 14px' }}
          >
            Вперёд →
          </button>
        </div>
      )}
    </>
  );
}
