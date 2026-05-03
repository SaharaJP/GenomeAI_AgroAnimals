'use client';
import { useState, useId } from 'react';
import type { ChartSeries } from '@/lib/api/analytics';

// SVG viewBox constants
const W = 560;
const H = 170;
const PL = 36; // left pad (Y labels)
const PR = 6;  // right pad
const PT = 10; // top pad
const PB = 24; // bottom pad (X labels)
const IW = W - PL - PR;
const IH = H - PT - PB;

interface Props {
  type: 'line' | 'stacked-bar';
  series: ChartSeries[];
  labels: string[];
  unit?: string;
  refLine?: number;
}

function fmtVal(v: number, unit: string): string {
  const abs = Math.abs(v);
  const s = abs >= 1000 ? `${(v / 1000).toFixed(1)}k` : Number.isInteger(v) ? String(v) : v.toFixed(1);
  return `${s}${unit}`;
}

export function BiChart({ type, series, labels, unit = '', refLine }: Props) {
  const [hovered, setHovered] = useState<number | null>(null);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const n = labels.length;

  if (n === 0 || series.length === 0) return null;

  // Y domain
  let yMin: number, yMax: number;
  if (type === 'line') {
    const all = series.flatMap(s => s.data);
    yMin = Math.min(...all);
    yMax = Math.max(...all);
  } else {
    const totals = Array.from({ length: n }, (_, i) =>
      series.reduce((a, s) => a + Math.max(0, s.data[i] ?? 0), 0),
    );
    yMin = 0;
    yMax = Math.max(...totals, 1);
  }
  const yRange = yMax === yMin ? 1 : yMax - yMin;

  const getX = (i: number) => PL + (i / Math.max(n - 1, 1)) * IW;
  const getY = (v: number) => PT + (1 - (v - yMin) / yRange) * IH;

  const barSlot = IW / n;
  const barW = barSlot * 0.62;

  const handleMouseMove = (e: React.MouseEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width;
    const viewX = relX * W;
    if (type === 'line') {
      const idx = Math.round(((viewX - PL) / IW) * (n - 1));
      setHovered(Math.max(0, Math.min(n - 1, idx)));
    } else {
      const idx = Math.floor((viewX - PL) / barSlot);
      setHovered(Math.max(0, Math.min(n - 1, idx)));
    }
  };

  const yTicks = [0, 0.5, 1].map(t => ({ y: PT + t * IH, v: yMax - t * yRange }));
  const tipX = hovered !== null ? getX(hovered) : 0;
  const tipLeftPct = hovered !== null ? `${Math.max(5, Math.min(75, (tipX / W) * 100))}%` : '0%';

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      {/* Tooltip */}
      {hovered !== null && (
        <div style={{
          position: 'absolute',
          top: 2,
          left: tipLeftPct,
          transform: 'translateX(-50%)',
          background: '#1e293b',
          color: '#fff',
          padding: '5px 10px',
          borderRadius: 4,
          fontSize: 11,
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
          zIndex: 10,
          boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          lineHeight: 1.75,
        }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, marginBottom: 2 }}>
            {labels[hovered]}
          </div>
          {series.map(s => (
            <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{
                width: 8, height: 8,
                borderRadius: type === 'line' ? '50%' : 2,
                background: s.color,
                display: 'inline-block',
                flexShrink: 0,
              }} />
              <span style={{ color: 'rgba(255,255,255,0.8)' }}>{s.name}:</span>
              <strong>{fmtVal(s.data[hovered] ?? 0, unit)}</strong>
            </div>
          ))}
        </div>
      )}

      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        style={{ width: '100%', height: H, display: 'block' }}
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={`grad-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={series[0].color} stopOpacity="0.14" />
            <stop offset="100%" stopColor={series[0].color} stopOpacity="0" />
          </linearGradient>
          <clipPath id={`clip-${uid}`}>
            <rect x={PL} y={PT} width={IW} height={IH} />
          </clipPath>
        </defs>

        {/* Grid lines + Y labels */}
        {yTicks.map(({ y, v }, i) => (
          <g key={i}>
            <line x1={PL} y1={y} x2={W - PR} y2={y} stroke="var(--border)" strokeWidth={0.75} />
            <text x={PL - 3} y={y + 3} fontSize={7.5} fill="var(--text-muted)" textAnchor="end">
              {fmtVal(v, unit)}
            </text>
          </g>
        ))}

        {/* Reference line (e.g. SCC 200k threshold) */}
        {refLine !== undefined && refLine >= yMin && refLine <= yMax && (
          <line
            x1={PL} y1={getY(refLine)} x2={W - PR} y2={getY(refLine)}
            stroke="var(--danger)"
            strokeWidth={1}
            strokeDasharray="4 3"
            opacity={0.55}
          />
        )}

        {/* X labels — every 4th week */}
        {labels.map((lbl, i) => i % 4 === 0 ? (
          <text key={i} x={getX(i)} y={H - 3} fontSize={7.5} fill="var(--text-muted)" textAnchor="middle">
            {lbl}
          </text>
        ) : null)}

        {type === 'line' ? (
          <g clipPath={`url(#clip-${uid})`}>
            {/* Area fill for first series */}
            {(() => {
              const pts = series[0].data
                .map((v, i) => `${getX(i).toFixed(1)},${getY(v).toFixed(1)}`)
                .join(' ');
              const bot = (PT + IH).toFixed(1);
              return (
                <polygon
                  points={`${PL},${bot} ${pts} ${(PL + IW).toFixed(1)},${bot}`}
                  fill={`url(#grad-${uid})`}
                />
              );
            })()}

            {/* Lines */}
            {series.map(s => (
              <polyline
                key={s.name}
                points={s.data.map((v, i) => `${getX(i).toFixed(1)},${getY(v).toFixed(1)}`).join(' ')}
                fill="none"
                stroke={s.color}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray={s.dashed ? '4 3' : undefined}
              />
            ))}

            {/* Hover crosshair + dots */}
            {hovered !== null && (
              <>
                <line
                  x1={getX(hovered)} y1={PT} x2={getX(hovered)} y2={PT + IH}
                  stroke="var(--text-muted)" strokeWidth={0.75} strokeDasharray="2 2" opacity={0.45}
                />
                {series.map(s => (
                  <circle
                    key={s.name}
                    cx={getX(hovered)}
                    cy={getY(s.data[hovered] ?? 0)}
                    r={3.5}
                    fill={s.color}
                    stroke="#fff"
                    strokeWidth={1.5}
                  />
                ))}
              </>
            )}
          </g>
        ) : (
          // Stacked bar
          <g>
            {Array.from({ length: n }, (_, i) => {
              const cx = PL + (i + 0.5) * barSlot;
              const x = cx - barW / 2;
              const segs: { y: number; h: number; color: string }[] = [];
              let cum = 0;
              for (const s of series) {
                const val = Math.max(0, s.data[i] ?? 0);
                const sh = (val / yMax) * IH;
                const sy = PT + IH - ((cum + val) / yMax) * IH;
                cum += val;
                segs.push({ y: sy, h: Math.max(0, sh), color: s.color });
              }
              return (
                <g key={i}>
                  {segs.map((seg, j) => (
                    <rect
                      key={j}
                      x={x} y={seg.y}
                      width={barW} height={seg.h}
                      fill={seg.color}
                      opacity={hovered === i ? 1 : 0.83}
                    />
                  ))}
                </g>
              );
            })}
          </g>
        )}

        {/* Transparent interaction overlay */}
        <rect
          x={PL} y={PT} width={IW} height={IH}
          fill="transparent"
          style={{ cursor: 'crosshair' }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHovered(null)}
        />
      </svg>
    </div>
  );
}
