'use client';
import { useState, useEffect } from 'react';
import { X, Search } from 'lucide-react';

interface Metric {
  id: string;
  group: string;
  name: string;
  desc: string;
}

const METRICS: Metric[] = [
  // Production
  { id: 'milk_ecm',         group: 'Production',    name: 'Milk yield and ECM',                    desc: 'Daily milk yield and energy-corrected milk' },
  { id: 'fat_protein',      group: 'Production',    name: 'Fat & protein %',                       desc: 'Fat and protein percentage trends' },
  { id: 'scc',              group: 'Production',    name: 'Somatic Cell Count (SCC)',              desc: 'SCC with 200k threshold' },
  { id: 'fat_per_cow',      group: 'Production',    name: 'Fat yield per cow',                     desc: 'Daily fat yield per individual cow' },
  { id: 'protein_per_cow',  group: 'Production',    name: 'Protein yield per cow',                 desc: 'Daily protein yield per individual cow' },
  { id: 'milk_per_cow',     group: 'Production',    name: 'Milk yield per cow',                    desc: 'Average daily yield per cow' },
  { id: 'milk_visits',      group: 'Production',    name: 'Milk visits per cow',                   desc: 'Average daily milking visits' },
  // Feed
  { id: 'dmi',              group: 'Feed',          name: 'Dry Matter Intake (DMI)',               desc: 'Average daily dry matter intake' },
  { id: 'feed_cost',        group: 'Feed',          name: 'Feed cost',                             desc: 'Weekly feed cost per cow' },
  { id: 'feed_efficiency',  group: 'Feed',          name: 'Feed efficiency',                       desc: 'Milk yield per kg of feed' },
  // Reproduction
  { id: 'repro_rates',      group: 'Reproduction',  name: 'Reproduction rates',                    desc: 'Conception, pregnancy, insemination rates' },
  { id: 'days_open',        group: 'Reproduction',  name: 'Days open after calving',               desc: 'Days open by lactation number' },
  { id: 'calving_interval', group: 'Reproduction',  name: 'Calving interval',                      desc: 'Average interval between calvings' },
  { id: 'vwp',              group: 'Reproduction',  name: 'Calculated VWP',                        desc: 'Voluntary waiting period by lactation' },
  // Health
  { id: 'mastitis',         group: 'Health',        name: 'Cows with mastitis (#)',                desc: 'Weekly mastitis incidence count' },
  { id: 'health_issues',    group: 'Health',        name: 'Cows with health issues (#)',           desc: 'Stacked breakdown by health condition' },
  { id: 'culling_rate',     group: 'Health',        name: 'Culling rate',                          desc: 'Weekly culling rate percentage' },
  { id: 'treatment_count',  group: 'Health',        name: 'Treatment count',                       desc: 'Number of treatments per week' },
  // Behaviour
  { id: 'rumination',       group: 'Behaviour',     name: 'Rumination time',                       desc: 'Average daily rumination minutes' },
  { id: 'activity',         group: 'Behaviour',     name: 'Activity index',                        desc: 'Herd-level activity score trend' },
  // Herd composition
  { id: 'herd_size',        group: 'Herd comp.',    name: 'Herd size',                             desc: 'Total cows in herd over time' },
  { id: 'dim_distribution', group: 'Herd comp.',    name: 'DIM distribution',                      desc: 'Days in milk distribution by week' },
];

const GROUPS = Array.from(new Set(METRICS.map(m => m.group)));

interface Props {
  open: boolean;
  onClose: () => void;
  onAdd: (metricId: string) => void;
}

export function AddChartDialog({ open, onClose, onAdd }: Props) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open) setQuery('');
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
          {/* Tabs: Chart View / List View (visual only) */}
          <div style={{ display: 'flex', gap: 2, marginBottom: 12 }}>
            {['Карточки', 'Список'].map((label, i) => (
              <button key={i} style={{
                padding: '5px 14px',
                fontSize: 12,
                fontWeight: 500,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                background: i === 0 ? 'var(--bg-muted)' : 'transparent',
                color: i === 0 ? 'var(--text)' : 'var(--text-muted)',
                cursor: 'pointer',
              }}>
                {label}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <button
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
            return (
              <div key={group}>
                <div className="an-group-title">
                  <span>▸</span> {group}
                </div>
                <div className="an-metric-grid">
                  {items.map(metric => (
                    <button
                      key={metric.id}
                      className="an-metric-card"
                      onClick={() => onAdd(metric.id)}
                    >
                      {/* Mini chart preview placeholder */}
                      <div className="an-metric-preview" />
                      <div className="an-metric-card-title">{metric.name}</div>
                      <div className="an-metric-card-desc">{metric.desc}</div>
                    </button>
                  ))}
                </div>
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
