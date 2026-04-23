'use client';

import { useState } from 'react';

type Props = {
  data: number[];
  label: string;
  unit: string;
};

function buildPolyline(data: number[], w: number, h: number, padX: number, padY: number): string {
  if (data.length < 2) return '';
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max === min ? 1 : max - min;
  const innerW = w - padX * 2;
  const innerH = h - padY * 2;

  return data
    .map((v, i) => {
      const x = padX + (i / (data.length - 1)) * innerW;
      const y = padY + (1 - (v - min) / range) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

function buildArea(data: number[], w: number, h: number, padX: number, padY: number): string {
  if (data.length < 2) return '';
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max === min ? 1 : max - min;
  const innerW = w - padX * 2;
  const innerH = h - padY * 2;

  const points = data.map((v, i) => {
    const x = padX + (i / (data.length - 1)) * innerW;
    const y = padY + (1 - (v - min) / range) * innerH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const bottom = h - padY;
  const firstX = padX.toFixed(1);
  const lastX = (padX + innerW).toFixed(1);

  return `${firstX},${bottom} ${points.join(' ')} ${lastX},${bottom}`;
}

const W = 600;
const H = 140;
const PAD_X = 8;
const PAD_Y = 16;

export function InsightChart({ data, label, unit }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (!data || data.length === 0) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max === min ? 1 : max - min;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_Y * 2;

  const getX = (i: number) => PAD_X + (i / (data.length - 1)) * innerW;
  const getY = (v: number) => PAD_Y + (1 - (v - min) / range) * innerH;

  const fmt = (v: number) =>
    Math.abs(v) >= 1000
      ? `${(v / 1000).toFixed(1)}k`
      : Number.isInteger(v)
      ? `${v}`
      : `${v.toFixed(1)}`;

  const polyline = buildPolyline(data, W, H, PAD_X, PAD_Y);
  const area = buildArea(data, W, H, PAD_X, PAD_Y);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width;
    const viewX = relX * W;
    const idx = Math.round(((viewX - PAD_X) / innerW) * (data.length - 1));
    setHoveredIdx(Math.max(0, Math.min(data.length - 1, idx)));
  };

  const tooltipLeftPct =
    hoveredIdx !== null ? `${(getX(hoveredIdx) / W) * 100}%` : '0%';

  return (
    <div className="insight-chart-wrap">
      <div className="insight-chart-label">{label}</div>
      <div style={{ position: 'relative' }}>
        {hoveredIdx !== null && (
          <div className="insight-chart-tooltip" style={{ left: tooltipLeftPct }}>
            {fmt(data[hoveredIdx])}{unit}
          </div>
        )}
        <svg
          className="insight-chart-svg"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          aria-label={label}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredIdx(null)}
          style={{ cursor: 'crosshair', display: 'block' }}
        >
          <defs>
            <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.5, 1].map((t, i) => {
            const y = PAD_Y + t * innerH;
            return (
              <line
                key={i}
                x1={PAD_X}
                y1={y}
                x2={W - PAD_X}
                y2={y}
                stroke="var(--border)"
                strokeWidth={1}
              />
            );
          })}

          {/* Area fill */}
          <polygon points={area} fill="url(#chartAreaGrad)" />

          {/* Line */}
          <polyline
            points={polyline}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Hovered vertical line */}
          {hoveredIdx !== null && (
            <line
              x1={getX(hoveredIdx)}
              y1={PAD_Y}
              x2={getX(hoveredIdx)}
              y2={H - PAD_Y}
              stroke="var(--accent)"
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.5}
            />
          )}

          {/* All data point dots */}
          {data.map((v, i) => {
            const isHovered = i === hoveredIdx;
            const isLast = i === data.length - 1;
            return (
              <circle
                key={i}
                cx={getX(i)}
                cy={getY(v)}
                r={isHovered ? 5 : isLast ? 4 : 2.5}
                fill="var(--accent)"
                stroke="#fff"
                strokeWidth={isHovered || isLast ? 2 : 1}
              />
            );
          })}

          {/* Y-axis min/max labels */}
          <text
            x={W - PAD_X + 4}
            y={PAD_Y + 4}
            fontSize={9}
            fill="var(--text-muted)"
            textAnchor="start"
          >
            {fmt(max)}{unit}
          </text>
          <text
            x={W - PAD_X + 4}
            y={H - PAD_Y + 4}
            fontSize={9}
            fill="var(--text-muted)"
            textAnchor="start"
          >
            {fmt(min)}{unit}
          </text>
        </svg>
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 9,
          color: 'var(--text-muted)',
          marginTop: 2,
        }}
      >
        <span>-7 дней</span>
        <span>Сейчас</span>
      </div>
    </div>
  );
}
