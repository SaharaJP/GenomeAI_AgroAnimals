import Link from 'next/link';
import { Card, MetricCard } from '@/components/ui/card';
import type { DecisionIntelligenceResponse } from '@/lib/api/contracts';

export function DecisionIntelligenceWidgets({ data }: { data: DecisionIntelligenceResponse }) {
  return (
    <div className="grid">
      <div className="grid grid-3">
        <MetricCard title="Decisions" value={data.summary.total_decisions} />
        <MetricCard title="Accepted feedback" value={data.summary.accepted_feedback} />
        <MetricCard title="Acceptance rate" value={`${Math.round((data.summary.acceptance_rate || 0) * 100)}%`} />
      </div>
      <Card>
        <h3 className="card-title">Top actions</h3>
        {data.top_actions.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Action</th><th>Count</th></tr></thead>
              <tbody>
                {data.top_actions.map((item) => (
                  <tr key={item.action}><td>{item.action}</td><td>{item.count}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="card-subtitle">No decision-intelligence entries yet.</p>
        )}
        <div className="linked-inline-actions">
          <Link href="/decisions">Open decision trail</Link>
          <Link href="/support">Feedback / support</Link>
        </div>
      </Card>
    </div>
  );
}
