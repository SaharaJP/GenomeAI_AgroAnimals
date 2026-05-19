'use client';

import { useEffect, useState } from 'react';

interface Props {
  label?: string;
  onRetry?: () => void;
  /**
   * Seconds after which to surface a retry CTA. Defaults to 10s — long enough
   * for slow API responses on the demo farm, short enough to recover users
   * from a stuck endpoint without forcing a full page reload.
   */
  timeoutSec?: number;
  error?: string | null;
}

export function LoaderWithRetry({
  label = 'Загрузка…',
  onRetry,
  timeoutSec = 10,
  error,
}: Props) {
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (error) {
      setTimedOut(false);
      return undefined;
    }
    const t = window.setTimeout(() => setTimedOut(true), Math.max(1, timeoutSec) * 1000);
    return () => window.clearTimeout(t);
  }, [error, timeoutSec]);

  if (error) {
    return (
      <div className="card error-text loader-with-retry">
        <p style={{ marginTop: 0 }}>Не удалось загрузить данные</p>
        <p className="small-muted" style={{ marginTop: 4 }}>{error}</p>
        {onRetry ? (
          <button type="button" className="button button-secondary" onClick={onRetry}>
            Повторить
          </button>
        ) : null}
      </div>
    );
  }

  if (timedOut && onRetry) {
    return (
      <div className="card loader-with-retry">
        <p style={{ marginTop: 0 }}>{label}</p>
        <p className="small-muted" style={{ marginTop: 4 }}>
          Backend дольше {timeoutSec} с не отвечает. Можно повторить запрос.
        </p>
        <button type="button" className="button button-secondary" onClick={onRetry}>
          Повторить
        </button>
      </div>
    );
  }

  return <div className="card">{label}</div>;
}
