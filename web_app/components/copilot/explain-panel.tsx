'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';

const DEFAULT_DATA_VERSION = 'dv_demo_farm_v1';

function inferDataVersionFromTarget(target?: string): string | null {
  const raw = String(target || '');
  const match = raw.match(/(?:[?&])data_version=([^&]+)/);
  if (!match || !match[1]) return null;
  try {
    return decodeURIComponent(match[1]).trim() || null;
  } catch {
    return match[1].trim() || null;
  }
}

function formatAssistantError(detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return detail.map((item) => formatAssistantError(item)).filter(Boolean).join(' | ');
  if (detail && typeof detail === 'object') {
    const row = detail as Record<string, unknown>;
    if (typeof row.detail === 'string' && row.detail.trim()) return row.detail;
    if (typeof row.error === 'string' && row.error.trim()) return row.error;
    if (typeof row.message === 'string' && row.message.trim()) return row.message;
    return JSON.stringify(row);
  }
  return 'Ошибка запроса к ассистенту';
}

type ExplainPanelProps = {
  initialTarget: string;
  initialDataVersion?: string;
};

export function ExplainPanel({
  initialTarget,
  initialDataVersion,
}: ExplainPanelProps) {
  const [dataVersion, setDataVersion] = useState(
    initialDataVersion || inferDataVersionFromTarget(initialTarget) || DEFAULT_DATA_VERSION,
  );
  const [target, setTarget] = useState(initialTarget);
  const [result, setResult] = useState('');
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <ExplainabilityBlock
        reasons={[
          'Поведение ассистента управляется сервером.',
          'Этот интерфейс только передаёт запрос на бэкенд.',
          'Семантика payload согласована с Android-клиентом.',
        ]}
      />

      <Card>
        <div className="toolbar">
          <input
            className="input"
            value={dataVersion}
            onChange={(e: any) => setDataVersion(e.target.value)}
            placeholder="data_version"
          />
          <input
            className="input"
            value={target}
            onChange={(e: any) => setTarget(e.target.value)}
            placeholder="target"
          />
          <Button
            onClick={async () => {
              setError(null);
              setResult('');
              try {
                const response = await fetch('/api/backend/assistant/resolve-target', {
                  method: 'POST',
                  headers: { 'content-type': 'application/json' },
                  body: JSON.stringify({ data_version: dataVersion, target }),
                });
                const body = await response.json().catch(() => null);
                if (!response.ok) {
                  throw new Error(formatAssistantError(body?.detail ?? body));
                }
                setResult(JSON.stringify(body, null, 2));
              } catch (err) {
                setError(err instanceof Error ? err.message : 'Ошибка запроса к ассистенту');
              }
            }}
          >
            Выполнить запрос
          </Button>
        </div>
      </Card>

      {error ? <div className="card error-text">{error}</div> : null}
      {result ? (
        <Card>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{result}</pre>
        </Card>
      ) : null}
    </>
  );
}
