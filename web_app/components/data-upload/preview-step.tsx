'use client';
import { useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import { postCommit, type UploadPreviewResponse } from '@/lib/api/uploads-client';

interface Props {
  preview: UploadPreviewResponse;
  onCommitted: (count: number) => void;
  onCancel: () => void;
  onError: (msg: string) => void;
}

export function PreviewStep({ preview, onCommitted, onCancel, onError }: Props) {
  const [busy, setBusy] = useState(false);

  async function commit() {
    setBusy(true);
    try {
      const r = await postCommit(preview.preview_token);
      onCommitted(r.inserted);
    } catch (e) {
      const msg = String(e);
      if (msg.includes('token_expired')) onError('Сессия истекла, загрузите файл заново');
      else onError(msg);
    } finally {
      setBusy(false);
    }
  }

  const stat = (icon: React.ReactNode, color: string, label: string, n: number) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '6px 12px', borderRadius: 6,
      background: color + '15', color, fontSize: 13,
    }}>
      {icon}
      <strong>{n}</strong>
      <span>{label}</span>
    </div>
  );

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {stat(<CheckCircle2 size={14} />, '#10b981', 'готовы к загрузке', preview.valid)}
        {stat(<AlertTriangle size={14} />, '#f59e0b', 'дубликатов (пропустим)', preview.duplicates)}
        {stat(<XCircle size={14} />, '#ef4444', 'ошибок', preview.errors.length)}
      </div>

      {preview.errors.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Ошибки</div>
          <div style={{
            maxHeight: 200, overflowY: 'auto',
            border: '1px solid var(--border)', borderRadius: 6, padding: 8,
            fontSize: 12,
          }}>
            {preview.errors.slice(0, 20).map((e, i) => (
              <div key={i} style={{ padding: '3px 0' }}>
                <span style={{ color: 'var(--text-muted)' }}>Строка {e.row}</span>
                {e.field && <span style={{ color: 'var(--danger, #b00020)', marginLeft: 6 }}>[{e.field}]</span>}
                <span style={{ marginLeft: 6 }}>{e.message}</span>
              </div>
            ))}
            {preview.errors.length > 20 && (
              <div style={{ color: 'var(--text-muted)', marginTop: 6 }}>
                …и ещё {preview.errors.length - 20} ошибок
              </div>
            )}
          </div>
        </div>
      )}

      {preview.valid_rows_sample.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Превью валидных (первые 5)</div>
          <pre style={{
            maxHeight: 160, overflow: 'auto',
            background: 'var(--bg-muted)', padding: 8, borderRadius: 6,
            fontSize: 11, margin: 0,
          }}>
            {JSON.stringify(preview.valid_rows_sample, null, 2)}
          </pre>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button className="btn-outline" onClick={onCancel} disabled={busy}>Отмена</button>
        <button
          className="btn-primary"
          onClick={commit}
          disabled={busy || preview.valid === 0}
        >
          {busy ? 'Загружаю…' : `Подтвердить и загрузить (${preview.valid})`}
        </button>
      </div>
    </div>
  );
}
