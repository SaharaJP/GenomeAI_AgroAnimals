'use client';

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import Link from 'next/link';
import {
  fetchIntegrationsHealth,
  KIND_LABELS,
  patchIntegrationEnabled,
  STATUS_LABELS,
  triggerIntegrationSync,
  type IntegrationHealth,
  type IntegrationsHealthResponse,
  type IntegrationStatus,
} from '@/lib/api/integrations';
import { pathLabels } from '@/lib/navigation';
import { useAuth } from '@/components/auth/auth-provider';

const REFRESH_INTERVAL_MS = 30_000;

function groupByKind(items: IntegrationHealth[]): { kind: string; rows: IntegrationHealth[] }[] {
  const order: string[] = ['llm', 'batch_connector', 'external_system', 'iot_device', 'sensor_ingestion'];
  const buckets = new Map<string, IntegrationHealth[]>();
  for (const item of items) {
    const bucket = buckets.get(item.kind);
    if (bucket) {
      bucket.push(item);
    } else {
      buckets.set(item.kind, [item]);
    }
  }
  return order
    .filter((k) => buckets.has(k))
    .map((k) => ({ kind: k, rows: buckets.get(k) || [] }));
}

function StatusBadge({ status }: { status: IntegrationStatus }) {
  return (
    <span
      className={`integration-status integration-status--${status}`}
      aria-label={`Статус: ${STATUS_LABELS[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

type IntegrationRowProps = {
  row: IntegrationHealth;
  canManage: boolean;
  onToggled: (row: IntegrationHealth) => void;
  onSynced: (row: IntegrationHealth, result: { ok: boolean; message: string; duration_ms: number; detail: string | null }) => void;
};

function IntegrationRow({ row, canManage, onToggled, onSynced }: IntegrationRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const hasDetails = Boolean(
    row.last_sync_at || row.last_error || row.records_in_last_window != null || row.latency_ms != null,
  );
  const isAdminDisabled =
    row.status === 'disabled' && (row.note ?? '').startsWith('Отключено администратором');
  const targetEnabled = isAdminDisabled; // toggle flips: disabled → enable, anything else → disable

  const handleToggle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setToggling(true);
    setToggleError(null);
    try {
      await patchIntegrationEnabled(row.id, targetEnabled);
      onToggled(row);
    } catch (err) {
      setToggleError(err instanceof Error ? err.message : 'Не удалось переключить');
    } finally {
      setToggling(false);
    }
  };

  const handleSync = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setSyncing(true);
    try {
      const result = await triggerIntegrationSync(row.id);
      onSynced(row, result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Ошибка sync';
      onSynced(row, { ok: false, message: 'error', duration_ms: 0, detail: msg });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <li className="integration-row">
      <div className="integration-row__head-wrap" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button
          type="button"
          className="integration-row__head"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          disabled={!hasDetails}
          style={{ flex: 1 }}
        >
          <span className="integration-row__title">
            <span className="integration-row__name">{row.name}</span>
            <span className="integration-row__id">{row.id}</span>
          </span>
          <StatusBadge status={row.status} />
        </button>
        <Link
          href={`/admin/logs?source=${encodeURIComponent(row.id)}`}
          onClick={(e: React.MouseEvent) => e.stopPropagation()}
          style={{
            padding: '4px 10px',
            border: '1px solid var(--border, #d0d5dd)',
            borderRadius: 6,
            fontSize: 13,
            textDecoration: 'none',
            color: 'inherit',
          }}
          title="Открыть логи в /admin/logs"
        >
          Логи
        </Link>
        {canManage ? (
          <>
            <button
              type="button"
              className="integration-row__sync"
              onClick={handleSync}
              disabled={syncing}
              aria-label="Запустить синхронизацию"
              title="Запустить синхронизацию"
              style={{
                padding: '4px 10px',
                border: '1px solid var(--border, #d0d5dd)',
                borderRadius: 6,
                background: 'var(--surface, white)',
                cursor: syncing ? 'wait' : 'pointer',
                fontSize: 13,
              }}
            >
              {syncing ? 'Sync…' : 'Sync'}
            </button>
            <button
              type="button"
              className={`integration-row__toggle ${targetEnabled ? 'is-enable' : 'is-disable'}`}
              onClick={handleToggle}
              disabled={toggling}
              aria-label={targetEnabled ? 'Включить интеграцию' : 'Отключить интеграцию'}
              title={targetEnabled ? 'Включить' : 'Отключить'}
              style={{
                padding: '4px 10px',
                border: '1px solid var(--border, #d0d5dd)',
                borderRadius: 6,
                background: targetEnabled ? 'var(--surface-accent, #eef4ff)' : 'var(--surface, white)',
                cursor: toggling ? 'wait' : 'pointer',
                fontSize: 13,
              }}
            >
              {toggling ? '…' : targetEnabled ? 'Включить' : 'Отключить'}
            </button>
          </>
        ) : null}
      </div>
      {row.note ? <p className="integration-row__note">{row.note}</p> : null}
      {toggleError ? (
        <p className="integration-row__note" role="alert" style={{ color: 'var(--danger, #c0392b)' }}>
          {toggleError}
        </p>
      ) : null}
      {expanded && hasDetails ? (
        <dl className="integration-row__details">
          {row.last_sync_at ? (
            <div>
              <dt>Последний прогон</dt>
              <dd>{row.last_sync_at}</dd>
            </div>
          ) : null}
          {row.records_in_last_window != null ? (
            <div>
              <dt>Записей за окно</dt>
              <dd>{row.records_in_last_window}</dd>
            </div>
          ) : null}
          {row.latency_ms != null ? (
            <div>
              <dt>Latency</dt>
              <dd>{row.latency_ms} мс</dd>
            </div>
          ) : null}
          {row.last_error ? (
            <div>
              <dt>Последняя ошибка</dt>
              <dd>
                <code>{row.last_error}</code>
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </li>
  );
}

export function IntegrationsSurface() {
  const [data, setData] = useState<IntegrationsHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);

  const auth = useAuth() as { me: { user?: { permissions?: string[] } } | null };
  const canManage = (auth.me?.user?.permissions ?? []).includes('integrations.manage');
  const [toast, setToast] = useState<string | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 4500);
  }

  function handleSynced(row: IntegrationHealth, result: { ok: boolean; message: string; duration_ms: number; detail: string | null }) {
    if (result.ok) {
      showToast(`Sync ${row.name}: ✓ ${result.message} (${result.duration_ms}мс)`);
    } else {
      const tail = result.detail ? ` — ${result.detail}` : '';
      showToast(`Sync ${row.name}: ✗ ${result.message}${tail}`);
    }
    void reload();
  }

  const reload = async () => {
    try {
      const resp = await fetchIntegrationsHealth();
      setData(resp);
      setError(null);
      setLastFetchedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить статус интеграций');
    }
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const resp = await fetchIntegrationsHealth();
        if (!active) return;
        setData(resp);
        setError(null);
        setLastFetchedAt(new Date());
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Не удалось загрузить статус интеграций');
      }
    };
    void load();
    const interval = window.setInterval(() => void load(), REFRESH_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const grouped = useMemo(() => (data ? groupByKind(data.items) : []), [data]);
  const aggregateBreakdown = useMemo(() => {
    if (!data) return null;
    const counts = { ok: 0, degraded: 0, down: 0, disabled: 0 };
    for (const item of data.items) {
      counts[item.status as keyof typeof counts] += 1;
    }
    return { ...counts, total: data.items.length };
  }, [data]);
  const aggregateStatus: IntegrationStatus | null = useMemo(() => {
    if (!data) return null;
    const reals = data.items.filter((r) => r.status !== 'disabled');
    if (reals.length === 0) return 'disabled';
    if (reals.some((r) => r.status === 'down')) return 'down';
    if (reals.some((r) => r.status === 'degraded')) return 'degraded';
    return 'ok';
  }, [data]);

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">{pathLabels['/admin/integrations'] || 'Контроль интеграций'}</h1>
          <p className="page-subtitle">
            Обзор всех интеграций платформы: реальные (LLM, batch ingest) и запланированные
            (IoT, live RU-системы). Обновление автоматическое раз в 30 секунд. Admin может включать/отключать
            интеграции; manual sync и deep-link в логи — следующие итерации P1-6b.
          </p>
        </div>
        {aggregateStatus ? (
          <div
            className="integrations-aggregate"
            title={
              aggregateBreakdown
                ? [
                    `Всего: ${aggregateBreakdown.total}`,
                    `OK: ${aggregateBreakdown.ok}`,
                    `Деградация: ${aggregateBreakdown.degraded}`,
                    `Недоступно: ${aggregateBreakdown.down}`,
                    `Отключено/stub: ${aggregateBreakdown.disabled}`,
                  ].join(' · ')
                : undefined
            }
          >
            <span className="integrations-aggregate__label">Сводный статус</span>
            <StatusBadge status={aggregateStatus} />
            {aggregateBreakdown ? (
              <span style={{ fontSize: 12, color: 'var(--text-muted, #667085)' }}>
                ({aggregateBreakdown.ok}/{aggregateBreakdown.total - aggregateBreakdown.disabled} real ok, {aggregateBreakdown.disabled} stubs)
              </span>
            ) : null}
            {lastFetchedAt ? (
              <time className="integrations-aggregate__ts" dateTime={lastFetchedAt.toISOString()}>
                Обновлено: {lastFetchedAt.toLocaleTimeString('ru-RU')}
              </time>
            ) : null}
          </div>
        ) : null}
      </div>

      {error ? (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      ) : null}

      {!data ? (
        <Card>
          <p className="card-subtitle">Загрузка статусов…</p>
        </Card>
      ) : data.total === 0 ? (
        <EmptyState
          title="Интеграции не зарегистрированы"
          description="На платформе нет ни одного провайдера интеграций. Это ошибочное состояние — проверьте регистрацию в core.interoperability.providers."
        />
      ) : (
        grouped.map((bucket) => (
          <Card key={bucket.kind}>
            <h3 className="card-title">
              {KIND_LABELS[bucket.kind as keyof typeof KIND_LABELS] || bucket.kind}
              <span className="integrations-bucket__count"> · {bucket.rows.length}</span>
            </h3>
            <ul className="integration-list">
              {bucket.rows.map((row) => (
                <IntegrationRow
                  key={row.id}
                  row={row}
                  canManage={canManage}
                  onToggled={() => void reload()}
                  onSynced={handleSynced}
                />
              ))}
            </ul>
          </Card>
        ))
      )}

      <ExplainabilityBlock
        title="Контракт страницы"
        reasons={[
          'Каждая строка — один source-system (одна запись на «Селекс», «1С», «OpenAI»…), даже если у системы есть несколько внутренних конфигов.',
          'Цвет badge: ok=зелёный, degraded=жёлтый, down=красный, disabled=серый. Серый означает что интеграция в каталоге, но не активирована.',
          'Stub-строки (IoT, Хэрриот, sensor ingestion) указывают в note, в каком эпике появится реальная имплементация (P2-3 / P2-4).',
          'Секреты на странице не отображаются — только статус и метаданные (CLAUDE.md §6 «никаких токенов в payload»).',
          'Кнопка Sync (требует integrations.manage) запускает реальную проверку: для LLM = openai.models.list(), остальные пока not_supported.',
        ]}
      />

      {toast ? (
        <div className="toast" role="status" aria-live="polite">{toast}</div>
      ) : null}
    </div>
  );
}
