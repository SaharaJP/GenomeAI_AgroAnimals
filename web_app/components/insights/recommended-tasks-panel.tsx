'use client';

import { useEffect, useState } from 'react';
import { Trash2, Send, RefreshCcw } from 'lucide-react';
import { apiFetch } from '@/lib/api/client';
import type {
  RecommendedTask,
  RecommendedTasksListResponse,
  WorklistsFromRecommendedResponse,
} from '@/lib/api/contracts';

const PRIORITY_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: '1 — Срочно' },
  { value: 2, label: '2 — Высокий' },
  { value: 3, label: '3 — Средний' },
  { value: 4, label: '4 — Низкий' },
];

const ROLE_OPTIONS: string[] = ['Vet', 'Zootech', 'Director', 'Operator'];

function pushToast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export function RecommendedTasksPanel({ canManage = true }: { canManage?: boolean }) {
  const [items, setItems] = useState<RecommendedTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(() => new Set<string>());
  const [bulkBusy, setBulkBusy] = useState(false);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<RecommendedTasksListResponse>('/recommended-tasks');
      setItems(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  function updateField(id: string, field: keyof RecommendedTask, value: unknown) {
    setItems((prev) =>
      prev.map((it) => (it.recommended_task_id === id ? { ...it, [field]: value } : it)),
    );
  }

  function removeOne(id: string) {
    setItems((prev) => prev.filter((it) => it.recommended_task_id !== id));
  }

  async function postOne(item: RecommendedTask) {
    if (!canManage) {
      pushToast('Нет разрешения tasks.write.');
      return;
    }
    setBusyIds((s) => new Set(s).add(item.recommended_task_id));
    try {
      const res = await apiFetch<WorklistsFromRecommendedResponse>('/worklists/from-recommended', {
        method: 'POST',
        body: JSON.stringify({ items: [item] }),
      });
      const status = res.items[0];
      pushToast(
        status?.created
          ? `Задача поставлена: ${status.task_id.slice(0, 8)}…`
          : `Задача уже существовала: ${status?.task_id.slice(0, 8)}…`,
      );
      removeOne(item.recommended_task_id);
    } catch (e) {
      pushToast(`Ошибка: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyIds((s) => {
        const next = new Set(s);
        next.delete(item.recommended_task_id);
        return next;
      });
    }
  }

  async function postAll() {
    if (!canManage) {
      pushToast('Нет разрешения tasks.write.');
      return;
    }
    if (items.length === 0) return;
    setBulkBusy(true);
    try {
      const res = await apiFetch<WorklistsFromRecommendedResponse>('/worklists/from-recommended', {
        method: 'POST',
        body: JSON.stringify({ items }),
      });
      pushToast(`Создано ${res.created}, повторно использовано ${res.reused}.`);
      setItems([]);
    } catch (e) {
      pushToast(`Ошибка постановки: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <section
      className="card"
      style={{ marginTop: 24, padding: 20 }}
      aria-label="Рекомендованные задачи"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h2 className="card-title" style={{ margin: 0 }}>
            Рекомендованные задачи
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
            Автоматически сформированы из открытых инсайтов. Отредактируйте и поставьте — или
            удалите ненужные.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="button"
            onClick={() => void reload()}
            disabled={loading}
            title="Перечитать с сервера"
          >
            <RefreshCcw size={13} strokeWidth={2} style={{ marginRight: 6, verticalAlign: -2 }} />
            Обновить
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={() => void postAll()}
            disabled={!canManage || bulkBusy || items.length === 0}
            title={canManage ? undefined : 'Нет разрешения tasks.write'}
          >
            <Send size={13} strokeWidth={2} style={{ marginRight: 6, verticalAlign: -2 }} />
            {bulkBusy ? 'Ставлю задачи…' : `Поставить все (${items.length})`}
          </button>
        </div>
      </div>

      {loading && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загружаю…</div>}
      {error && <div className="error-text">{error}</div>}
      {!loading && !error && items.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          Нет рекомендованных задач (все инсайты обработаны или не содержат actionable полей).
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map((item) => (
          <RecommendedTaskCard
            key={item.recommended_task_id}
            item={item}
            busy={busyIds.has(item.recommended_task_id)}
            canManage={canManage}
            onChangeField={(f, v) => updateField(item.recommended_task_id, f, v)}
            onDelete={() => removeOne(item.recommended_task_id)}
            onSubmit={() => void postOne(item)}
          />
        ))}
      </div>
    </section>
  );
}

type CardProps = {
  item: RecommendedTask;
  busy: boolean;
  canManage: boolean;
  onChangeField: (field: keyof RecommendedTask, value: unknown) => void;
  onDelete: () => void;
  onSubmit: () => void;
};

function RecommendedTaskCard({ item, busy, canManage, onChangeField, onDelete, onSubmit }: CardProps) {
  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 14,
        background: 'var(--panel)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <input
        type="text"
        value={item.title}
        onChange={(e) => onChangeField('title', e.target.value)}
        className="input"
        style={{ fontWeight: 600, fontSize: 14 }}
        placeholder="Название задачи"
        aria-label="Название задачи"
      />

      <textarea
        value={item.description || ''}
        onChange={(e) => onChangeField('description', e.target.value)}
        className="input"
        rows={2}
        style={{ resize: 'vertical', fontSize: 13, color: 'var(--text-secondary)' }}
        placeholder="Описание задачи (контекст из инсайта)"
        aria-label="Описание задачи"
      />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, minWidth: 140 }}>
          <span style={{ color: 'var(--text-muted)' }}>Приоритет</span>
          <select
            value={item.priority}
            onChange={(e) => onChangeField('priority', Number(e.target.value))}
            className="input"
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, minWidth: 150 }}>
          <span style={{ color: 'var(--text-muted)' }}>Срок (опционально)</span>
          <input
            type="date"
            value={(item.due_at || '').slice(0, 10)}
            onChange={(e) => onChangeField('due_at', e.target.value || null)}
            className="input"
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, minWidth: 140 }}>
          <span style={{ color: 'var(--text-muted)' }}>Ответственный (роль)</span>
          <select
            value={item.assignee_role || ''}
            onChange={(e) => onChangeField('assignee_role', e.target.value || null)}
            className="input"
          >
            <option value="">— не задан —</option>
            {ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button
            type="button"
            className="button"
            onClick={onDelete}
            disabled={busy}
            title="Удалить рекомендацию из списка (задача не создаётся)"
          >
            <Trash2 size={13} strokeWidth={2} style={{ marginRight: 6, verticalAlign: -2 }} />
            Удалить
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={onSubmit}
            disabled={!canManage || busy}
            title={canManage ? undefined : 'Нет разрешения tasks.write'}
          >
            <Send size={13} strokeWidth={2} style={{ marginRight: 6, verticalAlign: -2 }} />
            {busy ? 'Ставлю…' : 'Поставить задачу'}
          </button>
        </div>
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        Из инсайта <code style={{ fontFamily: 'var(--mono, monospace)' }}>{item.source_insight_id}</code> · {item.why_summary}
      </div>
    </div>
  );
}
