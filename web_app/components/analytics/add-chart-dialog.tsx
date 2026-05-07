'use client';
import { useState, useEffect } from 'react';
import { X, Search } from 'lucide-react';

interface Metric {
  id: string;
  group: string;
  name: string;
  desc: string;
}

export const METRICS: Metric[] = [
  // Продуктивность
  { id: 'milk_ecm',         group: 'Продуктивность',   name: 'Надой и ECM',                         desc: 'Ежедневный надой и энергокорректированное молоко' },
  { id: 'fat_protein',      group: 'Продуктивность',   name: 'Жир и белок %',                       desc: 'Тренды жира и белка' },
  { id: 'scc',              group: 'Продуктивность',   name: 'Соматические клетки (СКК)',            desc: 'СКК с порогом 200k' },
  { id: 'fat_per_cow',      group: 'Продуктивность',   name: 'Выход жира на корову',                desc: 'Ежедневный выход жира на корову' },
  { id: 'protein_per_cow',  group: 'Продуктивность',   name: 'Выход белка на корову',               desc: 'Ежедневный выход белка на корову' },
  { id: 'milk_per_cow',     group: 'Продуктивность',   name: 'Надой на корову',                     desc: 'Средний ежедневный надой на корову' },
  { id: 'milk_visits',      group: 'Продуктивность',   name: 'Доений на корову',                    desc: 'Среднее число доений в день' },
  // Кормление
  { id: 'dmi',              group: 'Кормление',        name: 'Потребление сухого вещества (ПСВ)',   desc: 'Среднесуточное потребление СВ' },
  { id: 'feed_cost',        group: 'Кормление',        name: 'Стоимость корма',                     desc: 'Недельная стоимость корма на корову' },
  { id: 'feed_efficiency',  group: 'Кормление',        name: 'Эффективность кормления',             desc: 'Надой на кг корма' },
  // Воспроизводство
  { id: 'repro_rates',      group: 'Воспроизводство',  name: 'Показатели воспроизводства',          desc: 'Стельность, оплодотворяемость, осеменяемость' },
  { id: 'days_open',        group: 'Воспроизводство',  name: 'Дней до осеменения после отёла',      desc: 'Дни открытого периода по лактации' },
  { id: 'calving_interval', group: 'Воспроизводство',  name: 'Межотельный интервал',                desc: 'Средний интервал между отёлами' },
  { id: 'vwp',              group: 'Воспроизводство',  name: 'Расчётный ДОС',                       desc: 'Добровольный ожидаемый срок по лактации' },
  // Здоровье
  { id: 'mastitis',         group: 'Здоровье',         name: 'Коров с маститом (#)',                desc: 'Недельная заболеваемость маститом' },
  { id: 'health_issues',    group: 'Здоровье',         name: 'Коров с проблемами здоровья (#)',     desc: 'Разбивка по состояниям здоровья' },
  { id: 'culling_rate',     group: 'Здоровье',         name: 'Выбраковка',                          desc: 'Недельный процент выбраковки' },
  { id: 'treatment_count',  group: 'Здоровье',         name: 'Число лечений',                       desc: 'Количество лечений за неделю' },
  // Поведение
  { id: 'rumination',       group: 'Поведение',        name: 'Время жвачки',                        desc: 'Среднесуточное время жвачки (мин)' },
  { id: 'activity',         group: 'Поведение',        name: 'Индекс активности',                   desc: 'Тренд активности стада' },
  // Состав стада
  { id: 'herd_size',        group: 'Состав стада',     name: 'Размер стада',                        desc: 'Общее число коров в стаде' },
  { id: 'dim_distribution', group: 'Состав стада',     name: 'Распределение ДДМ',                   desc: 'Распределение дней доения за неделю' },
];

const GROUPS = Array.from(new Set(METRICS.map(m => m.group)));

interface Props {
  open: boolean;
  onClose: () => void;
  onAdd: (metricId: string) => void;
}

export function AddChartDialog({ open, onClose, onAdd }: Props) {
  const [query, setQuery] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'list'>('cards');
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery('');
      setActiveGroup(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const q = query.toLowerCase();
  const filtered = q
    ? METRICS.filter(m => m.name.toLowerCase().includes(q) || m.desc.toLowerCase().includes(q) || m.group.toLowerCase().includes(q))
    : METRICS;

  const filteredGroups = q ? Array.from(new Set(filtered.map(m => m.group))) : GROUPS;

  return (
    <div className="an-dialog-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="an-dialog" role="dialog" aria-modal="true" aria-label="Добавить график">
        <div className="an-dialog-header">
          <div>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Добавить графики на панель</h2>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              Список или карточки метрик
            </p>
          </div>
          <button className="an-dialog-close" onClick={onClose} aria-label="Закрыть">
            <X size={16} />
          </button>
        </div>

        <div className="an-dialog-body">
          {/* Tabs: Chart View / List View */}
          <div style={{ display: 'flex', gap: 2, marginBottom: 12 }}>
            {(['cards', 'list'] as const).map((mode) => {
              const label = mode === 'cards' ? 'Карточки' : 'Список';
              const active = viewMode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setViewMode(mode)}
                  aria-pressed={active}
                  style={{
                    padding: '5px 14px',
                    fontSize: 12,
                    fontWeight: 500,
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    background: active ? 'var(--bg-muted)' : 'transparent',
                    color: active ? 'var(--text)' : 'var(--text-muted)',
                    cursor: 'pointer',
                  }}
                >
                  {label}
                </button>
              );
            })}
            <div style={{ flex: 1 }} />
            <button
              type="button"
              onClick={() => {
                if (filtered.length > 0) onAdd(filtered[0].id);
              }}
              title="Добавить первую видимую метрику"
              style={{
                padding: '5px 14px',
                fontSize: 12,
                fontWeight: 500,
                border: '1px solid var(--accent)',
                borderRadius: 'var(--radius)',
                background: 'var(--accent-subtle)',
                color: 'var(--accent-text)',
                cursor: 'pointer',
              }}
            >
              + Добавить график
            </button>
          </div>

          {/* Search */}
          <div style={{ position: 'relative', marginBottom: 16 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              className="input"
              style={{ width: '100%', paddingLeft: 32, boxSizing: 'border-box' }}
              placeholder="Поиск метрик..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              autoFocus
            />
          </div>

          <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--text-muted)' }}>
            Поиск или просмотр метрик
          </p>

          {/* Metric groups */}
          {filteredGroups.map(group => {
            const items = filtered.filter(m => m.group === group);
            if (items.length === 0) return null;
            const collapsed = activeGroup !== null && activeGroup !== group;
            return (
              <div key={group}>
                <button
                  type="button"
                  onClick={() => setActiveGroup((g) => g === group ? null : group)}
                  className="an-group-title"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: 0, color: 'inherit', textAlign: 'left', width: '100%',
                  }}
                >
                  <span>{collapsed ? '▸' : '▾'}</span> {group}
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>
                    {items.length}
                  </span>
                </button>
                {!collapsed && (
                  viewMode === 'cards' ? (
                    <div className="an-metric-grid">
                      {items.map(metric => (
                        <button
                          key={metric.id}
                          type="button"
                          className="an-metric-card"
                          onClick={() => onAdd(metric.id)}
                        >
                          <div className="an-metric-preview" />
                          <div className="an-metric-card-title">{metric.name}</div>
                          <div className="an-metric-card-desc">{metric.desc}</div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 12 }}>
                      {items.map(metric => (
                        <button
                          key={metric.id}
                          type="button"
                          onClick={() => onAdd(metric.id)}
                          style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            gap: 12, padding: '8px 10px', borderRadius: 6,
                            border: '1px solid var(--border)', background: 'transparent',
                            cursor: 'pointer', textAlign: 'left', color: 'var(--text)',
                          }}
                        >
                          <span style={{ fontSize: 13, fontWeight: 600 }}>{metric.name}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1, textAlign: 'right' }}>
                            {metric.desc}
                          </span>
                        </button>
                      ))}
                    </div>
                  )
                )}
              </div>
            );
          })}

          {filtered.length === 0 && (
            <div className="empty-state" style={{ padding: '32px 0' }}>
              Метрики не найдены по запросу «{query}»
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
