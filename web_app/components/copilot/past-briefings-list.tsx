'use client';

import { useState } from 'react';
import type { WeeklyBrief } from '@/lib/weekly-briefs';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

function formatRu(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

type Props = {
  briefs: WeeklyBrief[];
  onSelect: (brief: WeeklyBrief) => void;
};

export function PastBriefingsList({ briefs, onSelect }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (briefs.length === 0) return null;

  return (
    <Card>
      <h2 className="card-title">Прошлые брифинги</h2>
      <div style={{ display: 'grid', gap: 6, marginTop: 14 }}>
        {briefs.map((brief) => {
          const isExpanded = expandedId === brief.brief_id;
          return (
            <div
              key={brief.brief_id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                overflow: 'hidden',
              }}
            >
              <button
                onClick={() => setExpandedId(isExpanded ? null : brief.brief_id)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  background: isExpanded ? 'var(--accent-subtle)' : 'var(--panel)',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>
                  {formatRu(brief.week_start)} — {formatRu(brief.week_end)}
                </span>
                {isExpanded ? (
                  <ChevronDown size={14} color="var(--text-muted)" />
                ) : (
                  <ChevronRight size={14} color="var(--text-muted)" />
                )}
              </button>

              {isExpanded && (
                <div
                  style={{
                    padding: '12px 14px',
                    borderTop: '1px solid var(--border)',
                    background: 'var(--bg-muted)',
                    display: 'grid',
                    gap: 10,
                  }}
                >
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {brief.summary}
                  </p>
                  <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-muted)' }}>
                    <span>Удой: {brief.kpis.avg_milk_yield_kg} кг</span>
                    <span>Здоровье: {brief.kpis.health_index_pct}%</span>
                    <span>Стельностей: {brief.kpis.conceptions_confirmed}</span>
                  </div>
                  <div>
                    <Button
                      className="button-secondary"
                      onClick={() => {
                        onSelect(brief);
                        setExpandedId(null);
                      }}
                      style={{ fontSize: 12, padding: '6px 12px' }}
                    >
                      Открыть брифинг
                    </Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
