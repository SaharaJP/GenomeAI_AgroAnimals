'use client';

import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  width?: number | string;
};

export function Modal({ open, onClose, title, children, width }: ModalProps) {
  const lastFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    lastFocused.current = (document.activeElement as HTMLElement) ?? null;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      lastFocused.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="ae-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="ae-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={width ? { width } : undefined}
      >
        <div className="ae-dialog-header">
          <h2 className="ae-dialog-title">{title}</h2>
          <button
            className="an-dialog-close"
            onClick={onClose}
            aria-label="Закрыть"
            type="button"
          >
            <X size={16} />
          </button>
        </div>
        <div className="ae-dialog-body">{children}</div>
      </div>
    </div>
  );
}
