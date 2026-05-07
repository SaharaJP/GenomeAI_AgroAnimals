'use client';
import { useState } from 'react';
import { Download, Upload as UploadIcon } from 'lucide-react';
import { templateUrl, postPreview, type UploadTypeMeta, type UploadPreviewResponse } from '@/lib/api/uploads-client';

interface Props {
  type: UploadTypeMeta;
  onPreview: (preview: UploadPreviewResponse) => void;
  onError: (msg: string) => void;
}

export function TemplateStep({ type, onPreview, onError }: Props) {
  const [busy, setBusy] = useState(false);

  async function handleFile(file: File) {
    setBusy(true);
    try {
      const preview = await postPreview(type.type, file);
      onPreview(preview);
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Тип: {type.label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>
        {type.instructions}
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Колонки</div>
        <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 6, padding: 8 }}>
          {type.columns.map((c) => (
            <div key={c.name} style={{ fontSize: 12, padding: '3px 0', display: 'flex', gap: 8 }}>
              <span style={{ fontWeight: 600, minWidth: 110 }}>{c.name}</span>
              <span style={{ color: c.required ? 'var(--danger, #b00020)' : 'var(--text-muted)' }}>
                {c.required ? 'обяз.' : 'опц.'}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>{c.kind}</span>
              <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{c.description}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <a className="btn-outline"
           href={templateUrl(type.type, 'csv')}
           download
           style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Download size={14} /> Скачать CSV
        </a>
        <a className="btn-outline"
           href={templateUrl(type.type, 'xlsx')}
           download
           style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Download size={14} /> Скачать XLSX
        </a>
      </div>

      <label style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        gap: 8, padding: 24, border: '2px dashed var(--border)',
        borderRadius: 8, cursor: busy ? 'wait' : 'pointer',
        background: 'var(--bg-muted)',
      }}>
        <UploadIcon size={28} color="var(--text-muted)" />
        <span style={{ fontSize: 13 }}>
          {busy ? 'Анализ файла…' : 'Перетащите файл или нажмите для выбора'}
        </span>
        <input
          type="file"
          accept=".csv,.xlsx"
          disabled={busy}
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
      </label>
    </div>
  );
}
