import Link from 'next/link';
import { Card } from '@/components/ui/card';

export function AssistantEntryPoints({
  objectType,
  objectId,
  dataVersion,
  reportVersion,
  contextLabel,
}: {
  objectType?: string;
  objectId?: string;
  dataVersion?: string | null;
  reportVersion?: string | null;
  contextLabel: string;
}) {
  const params = new URLSearchParams();
  if (objectType) params.set('object_type', objectType);
  if (objectId) params.set('object_id', objectId);
  if (dataVersion) params.set('data_version', dataVersion);
  if (reportVersion) params.set('report_version', reportVersion);
  params.set('target', contextLabel);
  return (
    <Card>
      <h3 className="card-title">Assistant entry points</h3>
      <p className="card-subtitle">Assistant remains backend-governed. React only forwards scoped context and version linkage.</p>
      <div className="linked-inline-actions">
        <Link href={`/assistant?${params.toString()}`}>Open assistant with this context</Link>
        {dataVersion ? <Link href={`/assistant?target=fact_pack&data_version=${encodeURIComponent(dataVersion)}`}>Fact-pack context</Link> : null}
        {reportVersion ? <Link href={`/assistant?target=report&report_version=${encodeURIComponent(reportVersion)}`}>Report context</Link> : null}
      </div>
    </Card>
  );
}
