'use client';
import { useEffect, useState } from 'react';
import { fetchAiCallDetail, type AiCallDetail } from '@/lib/api/admin-ai';

type Props = { callId: number | null; onClose: () => void };

export function AiCallTraceDrawer({ callId, onClose }: Props) {
  const [detail, setDetail] = useState<AiCallDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (callId == null) return;
    setDetail(null);
    setError(null);
    let active = true;
    fetchAiCallDetail(callId)
      .then((d) => {
        if (active) setDetail(d);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [callId]);

  if (callId == null) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-header">
          <h3>Trace #{callId}</h3>
          <button onClick={onClose} aria-label="Закрыть">✕</button>
        </header>
        <div className="drawer-body">
          {error && <div className="error-text">Ошибка загрузки: {error}</div>}
          {!detail && !error && <div className="muted">Загрузка…</div>}
          {detail && (
            <>
              <div className="grid grid-3">
                <div>
                  <div className="muted">Latency</div>
                  <div>{detail.latency_ms} мс</div>
                </div>
                <div>
                  <div className="muted">Токены</div>
                  <div>{detail.input_tokens + detail.output_tokens}</div>
                </div>
                <div>
                  <div className="muted">Стоимость</div>
                  <div>${detail.cost_usd.toFixed(4)}</div>
                </div>
              </div>
              <h4>Endpoint / model</h4>
              <p className="mono">{detail.endpoint} · {detail.model} · {detail.task_type}</p>
              {detail.error && (
                <>
                  <h4>Ошибка</h4>
                  <pre className="error-text">{detail.error}</pre>
                </>
              )}
              <h4>Prompt</h4>
              <pre className="trace-pre">{detail.prompt ?? '—'}</pre>
              <h4>Response</h4>
              <pre className="trace-pre">{detail.response ?? '—'}</pre>
              <h4>Evidence chips</h4>
              {detail.evidence_chips && detail.evidence_chips.length > 0 ? (
                <ul>
                  {detail.evidence_chips.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">— нет evidence —</p>
              )}
              <h4>Tools used</h4>
              {detail.tools_used && detail.tools_used.length > 0 ? (
                <pre className="trace-pre">{JSON.stringify(detail.tools_used, null, 2)}</pre>
              ) : (
                <p className="muted">— инструменты не вызывались —</p>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
