'use client';

import type { ImpactInterpretation, ImpactNarrative, ImpactSignificance } from '@/lib/api/impact-narrative';

const INTERPRETATION_COLOR: Record<ImpactInterpretation, string> = {
  positive: '#22c55e',
  negative: '#ef4444',
  neutral: '#6b7280',
  mixed: '#f97316',
};

const INTERPRETATION_LABEL: Record<ImpactInterpretation, string> = {
  positive: 'Позитивное',
  negative: 'Негативное',
  neutral: 'Нейтральное',
  mixed: 'Смешанное',
};

const SIGNIFICANCE_LABEL: Record<ImpactSignificance, string> = {
  major: 'Значительное',
  moderate: 'Умеренное',
  minor: 'Незначительное',
  insignificant: 'Плановое',
};

const SIGNIFICANCE_COLOR: Record<ImpactSignificance, string> = {
  major: '#ef4444',
  moderate: '#f97316',
  minor: '#6b7280',
  insignificant: '#22c55e',
};

function SignificanceBadge({ significance, interpretation }: {
  significance: ImpactSignificance;
  interpretation: ImpactInterpretation;
}) {
  const color = INTERPRETATION_COLOR[interpretation];
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 600,
      background: color + '18',
      color,
      border: `1px solid ${color}44`,
    }}>
      <span style={{
        display: 'inline-block',
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: SIGNIFICANCE_COLOR[significance],
      }} />
      {INTERPRETATION_LABEL[interpretation]} · {SIGNIFICANCE_LABEL[significance]}
    </span>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 80 ? '#22c55e' : pct >= 50 ? '#f97316' : '#6b7280';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, opacity: 0.7 }}>
      <span>Уверенность ИИ</span>
      <div style={{ width: 60, height: 4, borderRadius: 2, background: 'rgba(0,0,0,0.1)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span>{pct}%</span>
    </div>
  );
}

interface Props {
  narrative: ImpactNarrative;
}

export function ImpactNarrativeSection({ narrative }: Props) {
  return (
    <div style={{
      borderLeft: '3px solid #009688',
      paddingLeft: 12,
      marginTop: 12,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 8,
        flexWrap: 'wrap',
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#009688' }}>
          Интерпретация ИИ-помощника
        </span>
        <SignificanceBadge
          significance={narrative.significance}
          interpretation={narrative.interpretation}
        />
      </div>

      {/* Narrative text */}
      <p style={{
        fontSize: 13,
        lineHeight: 1.65,
        margin: 0,
        marginBottom: 10,
        opacity: 0.9,
      }}>
        {narrative.narrative}
      </p>

      {/* Recommendations */}
      {narrative.recommendations.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 600, opacity: 0.6, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Рекомендации
          </div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {narrative.recommendations.map((rec, i) => (
              <li key={i} style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 3, opacity: 0.85 }}>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
        <ConfidenceBar confidence={narrative.confidence} />
        <span style={{ fontSize: 10, opacity: 0.4 }}>
          Модель: {narrative.generation_model}
        </span>
      </div>
    </div>
  );
}
