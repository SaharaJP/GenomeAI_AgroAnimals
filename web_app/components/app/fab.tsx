'use client';

import { useEffect, useState } from 'react';
import { Plus, X, CalendarPlus, Sparkles, Upload } from 'lucide-react';
import { useAddEvent } from './add-event-context';
import { AskFarmWidget } from '@/components/ai/ask-farm-widget';
import { DataUploadDialog } from '@/components/data-upload/data-upload-dialog';

const menuItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  padding: '11px 16px',
  border: 'none',
  background: 'transparent',
  color: 'var(--text)',
  fontSize: 14,
  fontWeight: 500,
  cursor: 'pointer',
  textAlign: 'left',
  transition: 'background var(--duration-fast)',
};

export function FAB() {
  const { openDialog } = useAddEvent();
  const [menuOpen, setMenuOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen && !aiOpen && !uploadOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { setMenuOpen(false); setAiOpen(false); setUploadOpen(false); }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [menuOpen, aiOpen, uploadOpen]);

  function handleAddEvent() {
    setMenuOpen(false);
    openDialog();
  }

  function handleAskAI() {
    setMenuOpen(false);
    setAiOpen(true);
  }

  function handleUpload() {
    setMenuOpen(false);
    setUploadOpen(true);
  }

  return (
    <>
      {/* Backdrop that closes the popup menu */}
      {menuOpen && (
        <div
          onClick={() => setMenuOpen(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 49 }}
          aria-hidden
        />
      )}

      {/* Popup menu */}
      {menuOpen && (
        <div
          style={{
            position: 'fixed',
            bottom: 90,
            right: 24,
            background: 'var(--panel)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
            zIndex: 50,
            overflow: 'hidden',
            minWidth: 230,
          }}
          role="menu"
        >
          <button
            role="menuitem"
            onClick={handleAddEvent}
            style={menuItemStyle}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-muted)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
          >
            <CalendarPlus size={16} color="var(--accent)" />
            Добавить событие
          </button>
          <div style={{ height: 1, background: 'var(--border)', margin: '0 12px' }} />
          <button
            role="menuitem"
            onClick={handleAskAI}
            style={menuItemStyle}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-muted)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
          >
            <Sparkles size={16} color="var(--accent)" />
            Спросить ИИ-помощника
          </button>
          <div style={{ height: 1, background: 'var(--border)', margin: '0 12px' }} />
          <button
            role="menuitem"
            onClick={handleUpload}
            style={menuItemStyle}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-muted)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
          >
            <Upload size={16} color="var(--accent)" />
            Загрузить данные
          </button>
        </div>
      )}

      {/* AI assistant modal */}
      {aiOpen && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setAiOpen(false); }}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.45)',
            zIndex: 200,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
        >
          <div style={{ width: '100%', maxWidth: 580, position: 'relative' }}>
            <button
              onClick={() => setAiOpen(false)}
              aria-label="Закрыть ИИ-помощника"
              style={{
                position: 'absolute',
                top: -14,
                right: 0,
                width: 28,
                height: 28,
                borderRadius: '50%',
                border: 'none',
                background: 'var(--panel)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                zIndex: 1,
              }}
            >
              <X size={14} strokeWidth={2} />
            </button>
            <AskFarmWidget />
          </div>
        </div>
      )}

      {/* FAB button */}
      <button
        className="fab"
        onClick={() => setMenuOpen((prev) => !prev)}
        aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню действий'}
        title={menuOpen ? 'Закрыть' : 'Действия'}
        style={{ zIndex: 50, transition: 'background var(--duration-fast), transform var(--duration-fast)' }}
      >
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transform: menuOpen ? 'rotate(45deg)' : 'rotate(0deg)',
            transition: 'transform 200ms ease',
          }}
        >
          <Plus size={24} strokeWidth={2} />
        </span>
      </button>

      <DataUploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </>
  );
}
