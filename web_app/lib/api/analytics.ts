export interface ChartSeries {
  name: string;
  color: string;
  data: number[];
  dashed?: boolean;
}

export interface AnalyticsData {
  labels: string[];
  series: ChartSeries[];
}

// Mulberry32 — fast, seeded, deterministic
function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return function () {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

const N = 26; // 26 weekly data points

function makeLabels(): string[] {
  const months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
  const labels: string[] = [];
  const start = new Date(2025, 9, 6);
  for (let i = 0; i < N; i++) {
    const d = new Date(start.getTime() + i * 7 * 24 * 3600 * 1000);
    labels.push(`${String(d.getDate()).padStart(2, '0')} ${months[d.getMonth()]}`);
  }
  return labels;
}

export const WEEK_LABELS: string[] = makeLabels();

function walk(
  rng: () => number,
  base: number,
  variance: number,
  n: number,
  decimals = 1,
  lo?: number,
  hi?: number,
): number[] {
  const result: number[] = [];
  let v = base;
  const scale = Math.pow(10, decimals);
  const minV = lo ?? base * 0.45;
  const maxV = hi ?? base * 1.55;
  for (let i = 0; i < n; i++) {
    v += (rng() - 0.5) * variance * 2;
    v = Math.max(minV, Math.min(maxV, v));
    result.push(Math.round(v * scale) / scale);
  }
  return result;
}

// ── Production ──────────────────────────────────────────────────────────────

export function getProductionMilkEcm(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Milk yield', color: '#3B82F6', data: walk(mulberry32(1001), 30, 2.8, N) },
      { name: 'ECM yield', color: '#F59E0B', data: walk(mulberry32(1002), 33, 2.8, N) },
    ],
  };
}

export function getProductionFatProtein(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Fat %', color: '#3B82F6', data: walk(mulberry32(2001), 4.05, 0.3, N, 2, 3.2, 4.9) },
      { name: 'Protein %', color: '#10B981', data: walk(mulberry32(2002), 3.35, 0.18, N, 2, 2.8, 4.0) },
    ],
  };
}

export function getProductionScc(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      {
        name: 'SCC',
        color: '#EF4444',
        data: walk(mulberry32(3001), 185, 90, N, 0, 30, 500),
      },
    ],
  };
}

// ── Reproduction ────────────────────────────────────────────────────────────

export function getReproductionRates(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Conception rate', color: '#3B82F6', data: walk(mulberry32(4001), 35, 7, N, 0, 5, 75) },
      { name: 'Pregnancy rate', color: '#10B981', data: walk(mulberry32(4002), 22, 4.5, N, 0, 5, 65) },
      { name: 'Insemination rate', color: '#F59E0B', data: walk(mulberry32(4003), 62, 9, N, 0, 10, 90) },
    ],
  };
}

export function getReproductionDaysOpen(): AnalyticsData {
  const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4', '#EC4899'];
  return {
    labels: WEEK_LABELS,
    series: [1, 2, 3, 4, 5, 6, 7].map((lac, i) => ({
      name: `L${lac}`,
      color: COLORS[i],
      data: walk(mulberry32(4100 + i), 90 + i * 9, 16, N, 0, 20, 300),
    })),
  };
}

export function getReproductionVwp(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Lactation 1', color: '#3B82F6', data: walk(mulberry32(5001), 50, 5, N, 0) },
      { name: 'Lactation 2+', color: '#10B981', data: walk(mulberry32(5002), 56, 6, N, 0) },
    ],
  };
}

export function getReproductionVwpYoungstock(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Avg age at first breeding', color: '#F59E0B', data: walk(mulberry32(6001), 425, 28, N, 0) },
      { name: 'Youngstock VWP', color: '#3B82F6', data: walk(mulberry32(6002), 435, 22, N, 0) },
    ],
  };
}

// ── Health ──────────────────────────────────────────────────────────────────

export function getHealthMastitis(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Cows with mastitis', color: '#3B82F6', data: walk(mulberry32(7001), 8, 4, N, 0, 0, 30) },
    ],
  };
}

export function getHealthIssues(): AnalyticsData {
  const categories = [
    { name: 'Mastitis',           color: '#EF4444', base: 7,   v: 3   },
    { name: 'Lameness',           color: '#F59E0B', base: 4,   v: 2   },
    { name: 'Ketosis',            color: '#8B5CF6', base: 3,   v: 2   },
    { name: 'Metritis',           color: '#3B82F6', base: 2,   v: 1.5 },
    { name: 'Milk fever',         color: '#10B981', base: 1.5, v: 1   },
    { name: 'Retained placenta',  color: '#06B6D4', base: 1.5, v: 1   },
    { name: 'Diarrhea',           color: '#F97316', base: 1,   v: 0.8 },
    { name: 'Pneumonia',          color: '#EC4899', base: 1,   v: 0.8 },
    { name: 'Other',              color: '#94A3B8', base: 2,   v: 1   },
  ];
  return {
    labels: WEEK_LABELS,
    series: categories.map((c, i) => ({
      name: c.name,
      color: c.color,
      data: walk(mulberry32(8000 + i), c.base, c.v, N, 0, 0, 25),
    })),
  };
}
