'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import {
  approveMorningBrief,
  fetchMorningBrief,
  morningBriefPdfUrl,
  regenerateMorningBrief,
  type MorningBrief,
  type TodayAction,
} from '@/lib/api/morning-brief';
import { renderWithEntityLinks } from './entity-links';

const PRIORITY_LABEL: Record<TodayAction['priority'], string> = {
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
};
const PRIORITY_CLASS: Record<TodayAction['priority'], string> = {
  high: 'badge badge-danger',
  medium: 'badge badge-warning',
  low: 'badge badge-success',
};
const ROLE_LABEL: Record<TodayAction['role'], string> = {
  vet: 'Ветврач',
  zootech: 'Зоотехник',
  operator: 'Оператор',
  director: 'Директор',
};

// ── Editable action row ──────────────────────────────────────────────────────

interface ActionRowProps {
  action: TodayAction;
  index: number;
  onUpdate: (index: number, updated: TodayAction) => void;
  onDelete: (index: number) => void;
  initialEditing?: boolean;
}

function ActionRow({ action, index, onUpdate, onDelete, initialEditing = false }: ActionRowProps) {
  const [editing, setEditing] = useState(initialEditing);
  const [draft, setDraft] = useState<TodayAction>(action);

  function save() {
    onUpdate(index, draft);
    setEditing(false);
  }
  function cancel() {
    setDraft(action);
    setEditing(false);
  }

  return (
    <div className={`brief-action-row${editing ? ' brief-action-row--editing' : ''}`}>
      {!editing && (
        <div className="brief-action-view">
          <span className={`${PRIORITY_CLASS[action.priority]} brief-action-badge`}>
            {PRIORITY_LABEL[action.priority]}
          </span>
          <span className="brief-action-text">
            {renderWithEntityLinks(action.action)}
            {action.due && <span className="brief-action-due"> · {action.due}</span>}
          </span>
          <span className="brief-action-role">{ROLE_LABEL[action.role]}</span>
          <div className="brief-action-controls">
            <button type="button" className="brief-icon-btn" title="Редактировать" onClick={() => setEditing(true)}>✏</button>
            <button type="button" className="brief-icon-btn brief-icon-btn--danger" title="Удалить задачу" onClick={() => onDelete(index)}>✕</button>
          </div>
        </div>
      )}
      {editing && (
        <div className="brief-edit-form">
          <input
            className="brief-edit-input"
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
            placeholder="Описание задачи"
          />
          <div className="brief-edit-row">
            <span className="brief-edit-label">Приоритет:</span>
            <div className="brief-priority-picker">
              {(['high', 'medium', 'low'] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`brief-priority-pill brief-priority-pill--${p}${draft.priority === p ? ' brief-priority-pill--active' : ''}`}
                  onClick={() => setDraft({ ...draft, priority: p })}
                >
                  {PRIORITY_LABEL[p]}
                </button>
              ))}
            </div>
            <select
              className="brief-edit-select"
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value as TodayAction['role'] })}
            >
              {(['vet', 'zootech', 'operator', 'director'] as const).map((r) => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
            <input
              type="time"
              className="brief-edit-select brief-edit-time"
              value={draft.due ?? ''}
              onChange={(e) => setDraft({ ...draft, due: e.target.value || null })}
            />
          </div>
          <div className="brief-edit-actions">
            <button type="button" className="button button-primary brief-edit-btn" onClick={save}>Сохранить</button>
            <button type="button" className="button brief-edit-btn--cancel" onClick={cancel}>Отмена</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Collapsible section ──────────────────────────────────────────────────────

function CollapsibleSection({ title, defaultOpen = true, children }: {
  title: string; defaultOpen?: boolean; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="brief-section">
      <button type="button" className="brief-section-hdr" onClick={() => setOpen((x) => !x)}>
        <span className="brief-section-arrow">{open ? '▼' : '▶'}</span>
        {title}
      </button>
      {open && <div className="brief-section-body">{children}</div>}
    </div>
  );
}

// ── Empty / error state ──────────────────────────────────────────────────────

function BriefEmpty({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <section className="card">
      <div className="brief-ai-label"><span className="brief-ai-dot" /> ИИ-брифинг</div>
      <div className="card-title brief-empty-title">Брифинг будет готов в 06:00</div>
      <p className="brief-empty-desc">
        Ежедневный брифинг генерируется автоматически каждое утро в 06:00 МСК.
      </p>
      <button type="button" className="button button-primary" onClick={onGenerate} disabled={generating}>
        {generating ? 'Генерирую…' : 'Сгенерировать сейчас'}
      </button>
    </section>
  );
}

// ── Main card ────────────────────────────────────────────────────────────────

export function MorningBriefCard({ farmId = 'demo-farm-v1' }: { farmId?: string }) {
  const [brief, setBrief] = useState<MorningBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editedActions, setEditedActions] = useState<TodayAction[]>([]);
  const [newActionIndex, setNewActionIndex] = useState<number | null>(null);
  const [approved, setApproved] = useState(false);
  const [approving, setApproving] = useState(false);
  const [tasksCreated, setTasksCreated] = useState(0);

  function loadBrief() {
    setLoading(true);
    setError(null);
    setApproved(false);
    void fetchMorningBrief(farmId)
      .then((b) => { setBrief(b); setEditedActions(b.today_actions); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadBrief(); }, [farmId]);

  function handleRegenerate() {
    setGenerating(true);
    setError(null);
    setApproved(false);
    void regenerateMorningBrief(farmId)
      .then((b) => { setBrief(b); setEditedActions(b.today_actions); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setGenerating(false));
  }

  function updateAction(index: number, updated: TodayAction) {
    setEditedActions((prev) => prev.map((a, i) => (i === index ? updated : a)));
    setNewActionIndex(null);
  }
  function deleteAction(index: number) {
    setEditedActions((prev) => prev.filter((_, i) => i !== index));
    setNewActionIndex(null);
  }
  function addAction() {
    setEditedActions((prev) => {
      const next = [...prev, { action: '', priority: 'low' as const, due: null, role: 'operator' as const }];
      setNewActionIndex(next.length - 1);
      return next;
    });
  }

  async function handleApprove() {
    if (!brief) return;
    setApproving(true);
    try {
      const result = await approveMorningBrief(brief.brief_id, editedActions, farmId);
      setTasksCreated(result.tasks_created);
      setApproved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApproving(false);
    }
  }

  const updatedAgo = (() => {
    if (!brief) return '';
    try {
      const ms = Date.now() - new Date(brief.generated_at_utc + 'Z').getTime();
      const h = Math.floor(ms / 3600000);
      const m = Math.floor((ms % 3600000) / 60000);
      if (h > 0) return `${h} ч назад`;
      if (m > 0) return `${m} мин назад`;
      return 'только что';
    } catch { return ''; }
  })();

  if (loading) {
    return (
      <section className="card">
        <div className="brief-ai-label"><span className="brief-ai-dot" /> ИИ-брифинг</div>
        <div className="brief-loading">Загрузка брифинга…</div>
      </section>
    );
  }

  if (!brief) return <BriefEmpty onGenerate={handleRegenerate} generating={generating} />;

  return (
    <section className="card">
      {/* Header — no PDF button here */}
      <div className="brief-header">
        <div className="brief-ai-label">
          <span className="brief-ai-dot" />
          ИИ-брифинг
        </div>
        <div className="brief-header-right">
          {updatedAgo && <span className="brief-meta">обновлено {updatedAgo}</span>}
          <button type="button" className="button brief-refresh-btn"
            onClick={handleRegenerate} disabled={generating}>
            {generating ? '…' : '↺ Обновить'}
          </button>
        </div>
      </div>

      <h2 className="brief-headline">{brief.headline}</h2>
      <p className="brief-takeaway">{renderWithEntityLinks(brief.main_takeaway)}</p>

      {brief.overnight_changes.length > 0 && (
        <CollapsibleSection title="За ночь">
          {brief.overnight_changes.map((ch, i) => (
            <div key={i} className="brief-change-row">{renderWithEntityLinks(ch.text)}</div>
          ))}
        </CollapsibleSection>
      )}

      <CollapsibleSection title="Требует внимания">
        {editedActions.length > 0 && (
          <div className="brief-section-hdr-hint">
            {editedActions.length} {editedActions.length === 1 ? 'задача' : 'задач'} · наведите для редактирования
          </div>
        )}
        {editedActions.map((act, i) => (
          <ActionRow
            key={i}
            action={act}
            index={i}
            onUpdate={updateAction}
            onDelete={deleteAction}
            initialEditing={i === newActionIndex}
          />
        ))}
        <button type="button" className="brief-add-btn" onClick={addAction}>
          ＋ Добавить задачу вручную
        </button>
      </CollapsibleSection>

      {brief.notes.length > 0 && (
        <CollapsibleSection title="На заметку" defaultOpen={false}>
          {brief.notes.map((note, i) => (
            <div key={i} className="brief-note">{note}</div>
          ))}
        </CollapsibleSection>
      )}

      {error && <div className="brief-error">{error}</div>}

      <div className="brief-footer-meta">
        Брифинг сгенерирован {new Date(brief.generated_at_utc + 'Z').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })} в 06:00
      </div>

      {!approved ? (
        <div className="brief-approve-zone">
          <p className="brief-approve-hint">
            <strong>Согласование</strong> поставит задачи ответственным специалистам
            и разблокирует выгрузку в PDF.
          </p>
          <button
            type="button"
            className="button btn-primary-teal"
            onClick={handleApprove}
            disabled={approving || editedActions.length === 0}
          >
            {approving ? 'Согласую…' : '✓ Согласовать и поставить задачи'}
          </button>
        </div>
      ) : (
        <div className="brief-approved-zone">
          <span className="brief-approved-msg">
            ✓ Согласовано · задачи поставлены {tasksCreated} специалист{tasksCreated === 1 ? 'у' : 'ам'}
          </span>
          <a
            href={morningBriefPdfUrl(brief.brief_id, farmId)}
            target="_blank"
            rel="noreferrer"
            className="button brief-pdf-link"
          >
            ⬇ Скачать PDF
          </a>
        </div>
      )}
    </section>
  );
}
