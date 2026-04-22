'use client';

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
  if (!data || data.length === 0) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const polyline = buildPolyline(data, W, H, PAD_X, PAD_Y);
  const area = buildArea(data, W, H, PAD_X, PAD_Y);

  const fmt = (v: number) =>
    Math.abs(v) >= 1000
      ? `${(v / 1000).toFixed(1)}k`
      : Number.isInteger(v)
      ? `${v}`
      : `${v.toFixed(1)}`;

  const innerW = W - PAD_X * 2;
  const lastPt = data[data.length - 1];
  const lastX = PAD_X + innerW;
  const lastY =
    PAD_Y + (1 - (lastPt - min) / (max === min ? 1 : max - min)) * (H - PAD_Y * 2);

  return (
    <div className="insight-chart-wrap">
      <div className="insight-chart-label">{label}</div>
      <svg
        className="insight-chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        aria-label={label}
      >
        <defs>
          <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {[0, 0.5, 1].map((t, i) => {
          const y = PAD_Y + t * (H - PAD_Y * 2);
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
        <polygon
          points={area}
          fill="url(#chartAreaGrad)"
        />

        {/* Line */}
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Last point dot */}
        <circle
          cx={lastX}
          cy={lastY}
          r={4}
          fill="var(--accent)"
          stroke="#fff"
          strokeWidth={2}
        />

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
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
        <span>-7 дней</span>
        <span>Сейчас</span>
      </div>
    </div>
  );
}
