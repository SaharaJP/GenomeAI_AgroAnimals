import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

export type ExplainabilityReason = {
  title: string;
  detail: string;
  source: 'alert' | 'worklist' | 'decision';
};

function badgeTone(source: ExplainabilityReason['source']): 'success' | 'warning' | 'danger' {
  if (source === 'alert') return 'danger';
  if (source === 'worklist') return 'warning';
  return 'success';
}

export function ObjectExplainabilityPanel({
  title = 'Explainability by object',
  reasons,
}: {
  title?: string;
  reasons: ExplainabilityReason[];
}) {
  return (
    <Card>
      <h3 className="card-title">{title}</h3>
      <p className="card-subtitle">Reusable UI model for object-level reasons, always sourced from backend DTOs and audit linkage.</p>
      <div className="grid" style={{ marginTop: 12 }}>
        {reasons.map((reason, index) => (
          <div className="explain-item" key={`${reason.source}-${reason.title}-${index}`}>
            <div className="toolbar" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>{reason.title}</strong>
              <Badge tone={badgeTone(reason.source)}>{reason.source}</Badge>
            </div>
            <div className="small-muted" style={{ marginTop: 8 }}>{reason.detail}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
