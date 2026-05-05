'use client';

import { useState, useEffect, useCallback } from 'react';
import { use } from 'react';
import Link from 'next/link';
import { Search, ChevronRight } from 'lucide-react';

type Animal = {
  animal_id: string;
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

function AnimalListPage() {
  const [animals, setAnimals] = useState<Animal[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const fetchAnimals = useCallback(async (q: string, pageNum: number) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(pageNum * PAGE_SIZE),
      });
      if (q) params.set('search', q);
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
    const t = setTimeout(() => { setPage(0); fetchAnimals(search, 0); }, 300);
    return () => clearTimeout(t);
  }, [search, fetchAnimals]);

  useEffect(() => {
    fetchAnimals(search, page);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div>
          <h1 className="page-title">Животные</h1>
          <p className="page-subtitle">Все животные на ферме ({total} голов)</p>
        </div>
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
                <th>Порода</th>
                <th>Статус</th>
                <th>Группа / Пен</th>
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
