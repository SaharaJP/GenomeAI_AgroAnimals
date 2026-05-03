'use client';

import { useState } from 'react';
import { InsightRecommendation } from '@/lib/api/insights';

type Props = {
  recommendations: InsightRecommendation[];
};

export function ActionChecklist({ recommendations }: Props) {
  const [checked, setChecked] = useState<Set<string>>(new Set<string>());

  const toggle = (id: string) => {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setChecked(next);
  };

  return (
    <ol className="action-checklist">
      {recommendations.map((rec, idx) => {
        const done = checked.has(rec.id);
        return (
          <li
            key={rec.id}
            className={`action-checklist-item${done ? ' action-checklist-done' : ''}`}
          >
            <input
              type="checkbox"
              checked={done}
              onChange={() => toggle(rec.id)}
              id={`rec-${rec.id}`}
            />
            <label htmlFor={`rec-${rec.id}`} style={{ cursor: 'pointer', flex: 1 }}>
              <span className="action-checklist-text">
                {idx + 1}. {rec.text}
              </span>
              {rec.deadline && (
                <div className="action-checklist-deadline">до {rec.deadline}</div>
              )}
            </label>
          </li>
        );
      })}
    </ol>
  );
}
