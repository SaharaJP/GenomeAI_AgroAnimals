'use client';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { fetchExtendedBundle } from '@/lib/api/extended-surfaces';
import type { PilotResponse, ReadinessResponse, ReadinessCheck } from '@/lib/api/contracts';

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--danger, #d33)',
  high:     'var(--danger, #d33)',
  warning:  'var(--warn, #c80)',
  warn:     'var(--warn, #c80)',
  info:     'var(--accent, #06c)',
  low:      'var(--muted, #888)',
};

const STATUS_COLORS: Record<string, string> = {
  pass:     'var(--success, #2a7)',
  passed:   'var(--success, #2a7)',
  ok:       'var(--success, #2a7)',
  warn:     'var(--warn, #c80)',
  warning:  'var(--warn, #c80)',
  fail:     'var(--danger, #d33)',
  failed:   'var(--danger, #d33)',
  blocked:  'var(--danger, #d33)',
};

function StatusPill({ value, palette }: { value: string; palette: Record<string, string> }) {
  const color = palette[value.toLowerCase()] ?? 'var(--muted, #888)';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 12,
        fontSize: 11,
        fontWeight: 600,
        background: color,
        color: '#fff',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
      }}
    >
      {value}
    </span>
  );
}

function ChecksTable({ checks }: { checks: ReadinessCheck[] }) {
  if (!checks.length) {
    return <div style={{ color: 'var(--muted, #888)', fontSize: 13 }}>Нет проверок.</div>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #e3e3e3)' }}>
            <th style={{ padding: '8px 4px' }}>Check</th>
            <th style={{ padding: '8px 4px' }}>Severity</th>
            <th style={{ padding: '8px 4px' }}>Status</th>
            <th style={{ padding: '8px 4px' }}>Message</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={c.check_id} style={{ borderBottom: '1px solid var(--border-faint, #f0f0f0)' }}>
              <td style={{ padding: '8px 4px', fontFamily: 'var(--mono, monospace)', fontSize: 12 }}>{c.check_id}</td>
              <td style={{ padding: '8px 4px' }}><StatusPill value={c.severity} palette={SEVERITY_COLORS} /></td>
              <td style={{ padding: '8px 4px' }}><StatusPill value={c.status} palette={STATUS_COLORS} /></td>
              <td style={{ padding: '8px 4px', color: 'var(--muted-strong, #555)' }}>{c.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourcePathsList({ paths }: { paths: Record<string, string> }) {
  const entries = Object.entries(paths);
  if (!entries.length) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
      {entries.map(([key, value]) => (
        <div key={key} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
          <span style={{ color: 'var(--muted, #888)', minWidth: 110 }}>{key}</span>
          <code style={{ fontFamily: 'var(--mono, monospace)', fontSize: 11, color: 'var(--muted-strong, #555)' }}>{value}</code>
        </div>
      ))}
    </div>
  );
}

export function PilotSurface() {
  const [payload, setPayload] = useState<PilotResponse | null>(null);
  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => { if (active) setPayload(bundle.pilot); });
    return () => { active = false; };
  }, []);

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Пилот</h1>
          <p className="page-subtitle">
            Сводка пилот-фермы: data versions, упакованные релизы, статус выгрузок.
          </p>
        </div>
      </div>
      {!payload ? (
        <div className="card">Загрузка данных пилота…</div>
      ) : (
        <>
          <div className="grid grid-3">
            <MetricCard title="Pilot packs" value={payload.summary.total_pilot_packs} />
            <MetricCard title="Latest data version" value={payload.summary.latest_data_version || '—'} />
            <MetricCard title="Latest pack" value={payload.summary.latest_pack_id || '—'} />
          </div>
          <Card>
            <h3 className="card-title">Последние пакеты</h3>
            {!payload.items.length ? (
              <div style={{ color: 'var(--muted, #888)', fontSize: 13 }}>Нет упакованных релизов.</div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #e3e3e3)' }}>
                      <th style={{ padding: '8px 4px' }}>Pack ID</th>
                      <th style={{ padding: '8px 4px' }}>Data version</th>
                      <th style={{ padding: '8px 4px' }}>Status</th>
                      <th style={{ padding: '8px 4px' }}>Files</th>
                      <th style={{ padding: '8px 4px' }}>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.items.slice(0, 10).map((item) => (
                      <tr key={item.pack_id} style={{ borderBottom: '1px solid var(--border-faint, #f0f0f0)' }}>
                        <td style={{ padding: '8px 4px', fontFamily: 'var(--mono, monospace)', fontSize: 12 }}>{item.pack_id}</td>
                        <td style={{ padding: '8px 4px' }}>{item.data_version || '—'}</td>
                        <td style={{ padding: '8px 4px' }}><StatusPill value={item.status} palette={STATUS_COLORS} /></td>
                        <td style={{ padding: '8px 4px' }}>{item.file_count}</td>
                        <td style={{ padding: '8px 4px', color: 'var(--muted, #888)' }}>{item.created_at || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

export function ReadinessSurface() {
  const [payload, setPayload] = useState<ReadinessResponse | null>(null);
  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => { if (active) setPayload(bundle.readiness); });
    return () => { active = false; };
  }, []);

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Готовность системы</h1>
          <p className="page-subtitle">
            Чек-лист готовности контура к pilot rollout: secret-leak gates, Postgres-only profile lockdown,
            миграции, audit retention, support-bundle. Соответствует CLAUDE.md §4 (operational rollout).
          </p>
        </div>
      </div>
      {!payload ? (
        <div className="card">Загрузка проверок готовности…</div>
      ) : (
        <>
          <div className="grid grid-3">
            <MetricCard
              title="Общий статус"
              value={payload.summary.overall_status}
            />
            <MetricCard
              title="Проверок всего"
              value={payload.summary.checks_total}
            />
            <MetricCard
              title="Warnings / Failed"
              value={`${payload.summary.warnings} / ${payload.summary.failed}`}
            />
          </div>

          <Card>
            <h3 className="card-title">Сводка по статусам</h3>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
              <span style={{ fontSize: 13 }}>
                ✅ <strong>{payload.summary.passed}</strong> passed
              </span>
              <span style={{ fontSize: 13 }}>
                ⚠️ <strong>{payload.summary.warnings}</strong> warnings
              </span>
              <span style={{ fontSize: 13 }}>
                ❌ <strong>{payload.summary.failed}</strong> failed
              </span>
              {payload.profile && (
                <span style={{ fontSize: 13, color: 'var(--muted, #888)', marginLeft: 'auto' }}>
                  profile: <code style={{ fontFamily: 'var(--mono, monospace)' }}>{payload.profile}</code>
                </span>
              )}
            </div>
          </Card>

          <Card>
            <h3 className="card-title">Проверки готовности</h3>
            <ChecksTable checks={payload.checks} />
          </Card>

          {payload.source_paths && Object.keys(payload.source_paths).length > 0 && (
            <Card>
              <h3 className="card-title">Источники данных</h3>
              <SourcePathsList paths={payload.source_paths} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
