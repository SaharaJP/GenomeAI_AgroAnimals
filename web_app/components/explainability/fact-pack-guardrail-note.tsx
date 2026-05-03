import { Card } from '@/components/ui/card';

export function FactPackGuardrailNote({ compact = false }: { compact?: boolean }) {
  return (
    <Card>
      <h3 className="card-title">Fact-pack only</h3>
      <p className="card-subtitle">
        Explainability, assistant context and decision widgets render only backend-provided linkage, reason codes and versioned facts.
        Frontend never invents factors or recalculates explanation logic.
      </p>
      {!compact ? (
        <ul className="bullet-list compact">
          <li>Source linkage stays visible: data_version / model_version / report_version.</li>
          <li>Assistant remains guardrailed and backend-governed.</li>
          <li>Any unknown value is shown as n/a rather than inferred.</li>
        </ul>
      ) : null}
    </Card>
  );
}
