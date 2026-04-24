'use client';

import { useRef, useState } from 'react';
import { Sparkles, Send, Copy, RotateCcw } from 'lucide-react';
import { askFarm, parseTextSegments, type EvidenceItem } from '@/lib/ai-client';
import { EvidenceChip } from './evidence-chip';
import { EvidenceDrawer } from './evidence-drawer';

const PRESET_QUESTIONS = [
  'Почему упал удой у Звёздочки?',
  'Кого рекомендуется выбраковать?',
  'Какие коровы в охоте сегодня?',
];

type WidgetState = 'idle' | 'loading' | 'done' | 'error';

function DotsAnimation() {
  return (
    <span style={{ display: 'inline-flex', gap: 3, alignItems: 'center' }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: 'var(--accent)',
            display: 'inline-block',
            animation: `ai-pulse 1.2s ${i * 0.2}s ease-in-out infinite`,
          }}
        />
      ))}
    </span>
  );
}

function ResponseRenderer({
  text,
  evidenceMap,
  onChipClick,
}: {
  text: string;
  evidenceMap: Map<string, EvidenceItem>;
  onChipClick: (item: EvidenceItem) => void;
}) {
  const segments = parseTextSegments(text);

  return (
    <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
      {segments.map((seg, i) => {
        if (seg.kind === 'text') {
          return <span key={i}>{seg.text}</span>;
        }
        const item = evidenceMap.get(seg.evidenceId);
        if (!item) {
          return (
            <span key={i} style={{ color: 'var(--accent-text)', fontSize: 11 }}>
              [{seg.evidenceId}]
            </span>
          );
        }
        return (
          <span key={i} style={{ margin: '0 2px' }}>
            <EvidenceChip item={item} onClick={onChipClick} />
          </span>
        );
      })}
    </div>
  );
}

export function AskFarmWidget() {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState('');
  const [state, setState] = useState<WidgetState>('idle');
  const [error, setError] = useState('');
  const [evidenceMap, setEvidenceMap] = useState<Map<string, EvidenceItem>>(new Map());
  const [drawerItem, setDrawerItem] = useState<EvidenceItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const sessionId = useRef<string>(
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2),
  );

  const submit = async (q: string) => {
    if (!q.trim() || state === 'loading') return;
    setState('loading');
    setResponse('');
    setError('');
    setEvidenceMap(new Map());

    const newMap = new Map<string, EvidenceItem>();

    try {
      for await (const event of askFarm(q.trim(), sessionId.current)) {
        if (event.type === 'token') {
          setResponse((prev) => prev + event.text);
        } else if (event.type === 'evidence') {
          newMap.set(event.item.id, event.item);
          setEvidenceMap(new Map(newMap));
        } else if (event.type === 'error') {
          setError(event.message);
          setState('error');
          return;
        }
      }
      setState('done');
    } catch {
      setError('Ошибка соединения с AI-сервисом.');
      setState('error');
    }
  };

  const handlePreset = (q: string) => {
    setQuestion(q);
    submit(q);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(question);
  };

  const handleReset = () => {
    setState('idle');
    setResponse('');
    setError('');
    setQuestion('');
    setEvidenceMap(new Map());
    sessionId.current =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2);
  };

  const handleCopy = () => {
    if (response) navigator.clipboard.writeText(response).catch(() => {});
  };

  const openDrawer = (item: EvidenceItem) => {
    setDrawerItem(item);
    setDrawerOpen(true);
  };

  return (
    <>
      <style>{`
        @keyframes ai-pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.85); }
          50% { opacity: 1; transform: scale(1); }
        }
      `}</style>

      <div className="col-card" style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {/* Header */}
        <div className="col-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={15} color="var(--accent)" />
            <span className="col-header-title">ИИ-помощник</span>
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Спросите о ферме</span>
        </div>

        <div className="col-content" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Input form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 6 }}>
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Задайте вопрос о ферме..."
              disabled={state === 'loading'}
              style={{
                flex: 1,
                padding: '7px 10px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border-strong)',
                fontSize: 13,
                background: state === 'loading' ? 'var(--bg-muted)' : 'var(--bg)',
                color: 'var(--text)',
                outline: 'none',
              }}
              aria-label="Вопрос к ИИ-помощнику"
            />
            <button
              type="submit"
              disabled={!question.trim() || state === 'loading'}
              aria-label="Отправить"
              style={{
                padding: '7px 10px',
                borderRadius: 'var(--radius)',
                border: 'none',
                background:
                  !question.trim() || state === 'loading' ? 'var(--bg-muted)' : 'var(--accent)',
                color: !question.trim() || state === 'loading' ? 'var(--text-muted)' : '#fff',
                cursor:
                  !question.trim() || state === 'loading' ? 'default' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Send size={14} />
            </button>
          </form>

          {/* Preset chips */}
          {state === 'idle' && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {PRESET_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => handlePreset(q)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-pill)',
                    border: '1px solid var(--border-strong)',
                    background: 'var(--panel-subtle)',
                    color: 'var(--text-secondary)',
                    fontSize: 12,
                    cursor: 'pointer',
                    lineHeight: 1.4,
                    textAlign: 'left',
                    transition: 'border-color var(--duration-fast)',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--accent)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--accent-text)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-strong)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Loading state */}
          {state === 'loading' && !response && (
            <div
              style={{
                fontSize: 12,
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 0',
              }}
            >
              <DotsAnimation />
              <span>ИИ-помощник думает...</span>
            </div>
          )}

          {/* Streaming / done response */}
          {(state === 'loading' || state === 'done') && response && (
            <div
              style={{
                padding: '10px 12px',
                background: 'var(--bg-muted)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
              }}
            >
              <ResponseRenderer
                text={response}
                evidenceMap={evidenceMap}
                onChipClick={openDrawer}
              />
              {state === 'loading' && (
                <span
                  style={{
                    display: 'inline-block',
                    width: 2,
                    height: 14,
                    background: 'var(--accent)',
                    marginLeft: 2,
                    animation: 'ai-pulse 0.8s ease-in-out infinite',
                    verticalAlign: 'text-bottom',
                  }}
                />
              )}
            </div>
          )}

          {/* Error */}
          {state === 'error' && (
            <div
              style={{
                fontSize: 12,
                color: 'var(--danger)',
                padding: '8px 10px',
                background: '#fef2f2',
                borderRadius: 'var(--radius)',
                border: '1px solid #fecaca',
              }}
            >
              {error || 'Произошла ошибка. Попробуйте ещё раз.'}
            </div>
          )}
        </div>

        {/* Footer actions */}
        {(state === 'done' || state === 'error') && (
          <div
            style={{
              display: 'flex',
              gap: 8,
              padding: '10px 14px',
              borderTop: '1px solid var(--border)',
            }}
          >
            <button
              type="button"
              onClick={handleReset}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                padding: '5px 10px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border-strong)',
                background: 'var(--bg)',
                color: 'var(--text-secondary)',
                fontSize: 12,
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              <RotateCcw size={12} />
              Ещё вопрос
            </button>
            {state === 'done' && response && (
              <button
                type="button"
                onClick={handleCopy}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '5px 10px',
                  borderRadius: 'var(--radius)',
                  border: '1px solid var(--border-strong)',
                  background: 'var(--bg)',
                  color: 'var(--text-secondary)',
                  fontSize: 12,
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                <Copy size={12} />
                Копировать
              </button>
            )}
          </div>
        )}
      </div>

      <EvidenceDrawer
        item={drawerItem}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </>
  );
}
