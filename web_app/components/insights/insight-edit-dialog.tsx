'use client';
import { useState } from 'react';
import { X, Plus, Trash } from 'lucide-react';
import { patchInsight } from '@/lib/api/insights-client';
import type { InsightItem, InsightRecommendation } from '@/lib/api/insights';

interface Props {
  insight: InsightItem;
  onClose: () => void;
  onSaved: (updated: InsightItem) => void;
}

export function InsightEditDialog({ insight, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(insight.title);
  const [body, setBody] = useState(insight.body);
  const [action, setAction] = useState(insight.action);
  const [recs, setRecs] = useState<InsightRecommendation[]>(insight.recommendations ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateRec(idx: number, patch: Partial<InsightRecommendation>) {
    setRecs((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }
  function addRec() {
    setRecs((prev) => [...prev, { id: `r${prev.length + 1}`, text: '' }]);
  }
  function removeRec(idx: number) {
    setRecs((prev) => prev.filter((_, i) => i !== idx));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchInsight(insight.insight_id, {
        title,
        body,
        action,
        recommendations: recs,
      });
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: 8,
    border: '1px solid var(--border)',
    borderRadius: 6,
    background: 'var(--bg)',
    color: 'var(--text)',
    fontSize: 13,
  };

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: 24,
        width: '100%',
        maxWidth: 640,
        maxHeight: '90vh',
        overflow: 'auto',
        position: 'relative',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
      }}>
        <button
          onClick={onClose}
          aria-label="Закрыть"
          style={{
            position: 'absolute', top: 12, right: 12,
            background: 'none', border: 'none',
            cursor: 'pointer', color: 'var(--text-secondary)',
          }}
        ><X size={18} /></button>
        <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>Изменить инсайт</h3>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Заголовок</div>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Текст</div>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={5}
            style={{ ...inputStyle, fontFamily: 'inherit', resize: 'vertical' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Действие</div>
          <input value={action} onChange={(e) => setAction(e.target.value)} style={inputStyle} />
        </label>

        <div style={{ marginBottom: 12 }}>
          <div style={{
            fontWeight: 600, marginBottom: 8,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>Рекомендации</span>
            <button onClick={addRec} className="btn-outline" style={{ padding: '4px 10px', fontSize: 12 }}>
              <Plus size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              Добавить
            </button>
          </div>
          {recs.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '6px 0' }}>
              Нет рекомендаций. Нажмите «Добавить», чтобы создать первую.
            </div>
          )}
          {recs.map((r, i) => (
            <div key={r.id ?? i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <input
                value={r.text}
                placeholder="Текст рекомендации"
                onChange={(e) => updateRec(i, { text: e.target.value })}
                style={{ ...inputStyle, flex: 1 }}
              />
              <input
                type="date"
                value={r.deadline ?? ''}
                onChange={(e) => updateRec(i, { deadline: e.target.value })}
                style={{ ...inputStyle, width: 150 }}
              />
              <button
                onClick={() => removeRec(i)}
                aria-label="Удалить рекомендацию"
                style={{
                  background: 'none', border: 'none',
                  cursor: 'pointer', color: 'var(--text-muted)',
                  padding: '0 4px',
                }}
              >
                <Trash size={14} />
              </button>
            </div>
          ))}
        </div>

        {error && (
          <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginBottom: 12 }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn-outline" onClick={onClose} disabled={saving}>
            Отмена
          </button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  );
}
