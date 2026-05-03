import { Card } from '@/components/ui/card';
import { AssistantInteractiveClient } from '@/components/operations/assistant-interactive-client';

const DEFAULT_DATA_VERSION = 'dv_demo_farm_v1';
const DEFAULT_TARGET = `genomeai://copilot/fact?data_version=${DEFAULT_DATA_VERSION}&section=modules.alerts_v2&table=top`;

function firstNonEmpty(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    const normalized = String(value || '').trim();
    if (normalized) return normalized;
  }
  return null;
}

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

export default async function AssistantPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const initialTarget = firstNonEmpty(params.target, DEFAULT_TARGET) || DEFAULT_TARGET;
  const initialDataVersion =
    firstNonEmpty(params.data_version, inferDataVersionFromTarget(initialTarget), DEFAULT_DATA_VERSION) || DEFAULT_DATA_VERSION;

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Assistant</h1>
          <p className="page-subtitle">Thin frontend surface for assistant target resolution via canonical backend API.</p>
        </div>
      </div>

      {Object.keys(params).length > 0 ? (
        <Card>
          <h3 className="card-title">Hook context</h3>
          <p className="card-subtitle">This page was opened from a linked action hook. The context below is passed to backend resolution only.</p>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(params, null, 2)}</pre>
        </Card>
      ) : null}

      <AssistantInteractiveClient initialTarget={initialTarget} initialDataVersion={initialDataVersion} />
    </div>
  );
}
