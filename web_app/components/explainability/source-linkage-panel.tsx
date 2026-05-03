import { Card } from '@/components/ui/card';

export function SourceLinkagePanel({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <Card>
      <h3 className="card-title">Source & version linkage</h3>
      <div className="meta-list">
        {items.map((item) => (
          <div className="meta-row" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </Card>
  );
}
