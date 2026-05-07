'use client';
import { useEffect, useState } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { fetchUploadTypes, type UploadTypeMeta, type UploadPreviewResponse } from '@/lib/api/uploads-client';
import { TypeGrid } from './type-grid';
import { TemplateStep } from './template-step';
import { PreviewStep } from './preview-step';

function toast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

interface Props {
  open: boolean;
  onClose: () => void;
}

type Step = 'type' | 'template' | 'preview';

export function DataUploadDialog({ open, onClose }: Props) {
  const [types, setTypes] = useState<UploadTypeMeta[]>([]);
  const [step, setStep] = useState<Step>('type');
  const [selected, setSelected] = useState<UploadTypeMeta | null>(null);
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep('type');
    setSelected(null);
    setPreview(null);
    setError(null);
    fetchUploadTypes()
      .then((r) => setTypes(r.items))
      .catch((e) => setError(String(e)));
  }, [open]);

  if (!open) return null;

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 220,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 24,
        width: '100%', maxWidth: 640, maxHeight: '90vh', overflow: 'auto',
        position: 'relative',
      }}>
        <button onClick={onClose} aria-label="Закрыть"
          style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer' }}>
          <X size={18} />
        </button>

        <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>
          {step !== 'type' && (
            <button
              onClick={() => {
                if (step === 'preview') setStep('template');
                else if (step === 'template') setStep('type');
              }}
              aria-label="Назад"
              style={{ background: 'none', border: 'none', cursor: 'pointer', marginRight: 6 }}>
              <ArrowLeft size={16} />
            </button>
          )}
          Загрузить данные
          {step === 'template' && selected && <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> — {selected.label}</span>}
        </h3>

        {error && (
          <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginBottom: 12 }}>
            {error}
          </div>
        )}

        {step === 'type' && (
          types.length === 0 && !error
            ? <div style={{ color: 'var(--text-muted)' }}>Загрузка типов…</div>
            : <TypeGrid types={types} onSelect={(t) => { setSelected(t); setStep('template'); setError(null); }} />
        )}

        {step === 'template' && selected && (
          <TemplateStep
            type={selected}
            onPreview={(p) => { setPreview(p); setStep('preview'); setError(null); }}
            onError={setError}
          />
        )}

        {step === 'preview' && preview && (
          <PreviewStep
            preview={preview}
            onCommitted={(n) => { toast(`Загружено строк: ${n}`); onClose(); }}
            onCancel={onClose}
            onError={setError}
          />
        )}
      </div>
    </div>
  );
}
