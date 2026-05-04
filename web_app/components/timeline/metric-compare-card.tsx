import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { MetricComparison } from '@/lib/api/timeline';

type Props = {
  metric: MetricComparison;
};

function formatVal(v: number, unit: string): string {
  const formatted = Number.isInteger(v) ? String(v) : v.toFixed(1);
  return `${formatted} ${unit}`;
}

function calcBarPct(value: number, maxDisplay: number): string {
  const pct = Math.min(100, (value / maxDisplay) * 100);
  return `${pct.toFixed(1)}%`;
}

const SIG_CLASS: Record<string, string> = {
  significant:     'stat-sig-badge stat-sig-badge--significant',
  not_significant: 'stat-sig-badge stat-sig-badge--not-significant',
  inconclusive:    'stat-sig-badge stat-sig-badge--inconclusive',
};

const SIG_LABELS: Record<string, string> = {
  significant:     'p<0.05',
  not_significant: 'n.s.',
  inconclusive:    '~',
};

export function MetricCompareCard({ metric }: Props) {
  const { label, unit, before_value, after_value, higher_is_better, max_display = 100 } = metric;

  const delta = after_value - before_value;
  const isGood = higher_is_better ? delta >= 0 : delta <= 0;
  const isNeutral = Math.abs(delta) < 0.05;

  const deltaClass = isNeutral
    ? 'metric-card-delta metric-card-delta--neutral'
    : isGood
    ? 'metric-card-delta metric-card-delta--good'
    : 'metric-card-delta metric-card-delta--bad';

  const DeltaIcon = isNeutral ? Minus : delta > 0 ? TrendingUp : TrendingDown;
  const deltaAbs = Math.abs(delta);
  const deltaFormatted = Number.isInteger(deltaAbs) ? String(deltaAbs) : deltaAbs.toFixed(1);

  const beforePct = calcBarPct(before_value, max_display);
  const afterPct = calcBarPct(after_value, max_display);

  const hasStat = metric.welch_t_pvalue !== undefined;
  const pVal = metric.welch_t_pvalue;
  const sig = metric.significance;
  const ci = metric.bootstrap_ci_95;

  return (
    <div className="metric-card">
      <div className="metric-card-title">{label}</div>

      {/* Before row */}
      <div className="metric-card-row">
        <span className="metric-card-row-label" style={{ color: '#3b82f6', fontWeight: 600 }}>До</span>
        <div className="metric-card-bar-wrap">
          <div className="metric-card-bar-bg-before" style={{ width: beforePct }} />
          <span className="metric-card-bar-value">{formatVal(before_value, unit)}</span>
        </div>
      </div>

      {/* After row */}
      <div className="metric-card-row" style={{ marginBottom: 0 }}>
        <span className="metric-card-row-label" style={{ color: '#0d9488', fontWeight: 600 }}>После</span>
        <div className="metric-card-bar-wrap">
          <div className="metric-card-bar-bg-after" style={{ width: afterPct }} />
          <span className="metric-card-bar-value">{formatVal(after_value, unit)}</span>
        </div>
      </div>

      {/* Delta + p-value row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
        <span className={deltaClass}>
          <DeltaIcon size={11} />
          {deltaFormatted} {unit}
        </span>

        {hasStat && sig && pVal !== undefined && (
          <span
            className={SIG_CLASS[sig] ?? 'stat-sig-badge stat-sig-badge--not-significant'}
            title={ci ? `95% CI: [${ci[0].toFixed(2)}, ${ci[1].toFixed(2)}]` : undefined}
          >
            {SIG_LABELS[sig]} · p={pVal < 0.001 ? '<0.001' : pVal.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  );
}
