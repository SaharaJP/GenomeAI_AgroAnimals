export interface ChartSeries {
  name: string;
  color: string;
  data: number[];
  dashed?: boolean;
}

export interface AnalyticsData {
  labels: string[];
  series: ChartSeries[];
  /** Optional ISO (YYYY-MM-DD) dates parallel to labels — used to align overlays. */
  iso_dates?: string[];
}

/**
 * Map an arbitrary ISO date to the chart's nearest week index using the
 * chart's own iso_dates (each entry = Monday of that week). This is the
 * preferred alignment path for live data — does NOT depend on the static
 * WEEK_LABELS window.
 *
 * Strategy:
 *   - Drop incident dates earlier than the first chart week → -1.
 *   - Drop incident dates after (last_week_monday + 7d) → -1.
 *   - Otherwise return index of the latest week whose Monday ≤ target.
 */
export function findChartIndex(isoDates: string[], targetIso: string): number {
  if (!isoDates || isoDates.length === 0 || !targetIso) return -1;
  const target = new Date(targetIso + 'T00:00:00Z').getTime();
  if (Number.isNaN(target)) return -1;
  const first = new Date(isoDates[0] + 'T00:00:00Z').getTime();
  const last = new Date(isoDates[isoDates.length - 1] + 'T00:00:00Z').getTime();
  if (target < first) return -1;
  if (target > last + 7 * 24 * 3600 * 1000) return -1;
  // Linear scan — N is small (≤104). Find the latest week whose Monday ≤ target.
  let idx = -1;
  for (let i = 0; i < isoDates.length; i++) {
    const wkStart = new Date(isoDates[i] + 'T00:00:00Z').getTime();
    if (wkStart <= target) idx = i;
    else break;
  }
  return idx;
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

function makeIsoDates(): string[] {
  const out: string[] = [];
  const start = new Date(2025, 9, 6);
  for (let i = 0; i < N; i++) {
    const d = new Date(start.getTime() + i * 7 * 24 * 3600 * 1000);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

export const WEEK_ISO_DATES: string[] = makeIsoDates();

/** Map an arbitrary ISO date (YYYY-MM-DD) to the index of the week
 *  it belongs to in WEEK_LABELS. Returns -1 if outside the chart range.
 */
export function findWeekIndex(iso: string): number {
  if (!iso) return -1;
  const target = new Date(iso + 'T00:00:00Z').getTime();
  const start = new Date(2025, 9, 6).getTime();
  if (target < start) return -1;
  const idx = Math.floor((target - start) / (7 * 24 * 3600 * 1000));
  if (idx < 0 || idx >= N) return -1;
  return idx;
}

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

// ── Feed ─────────────────────────────────────────────────────────────────────

export function getFeedDmi(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'DMI', color: '#3B82F6', data: walk(mulberry32(9001), 22, 1.8, N, 1) },
    ],
  };
}

export function getFeedCost(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Стоимость корма', color: '#F59E0B', data: walk(mulberry32(9002), 48, 4, N, 0) },
    ],
  };
}

export function getFeedEfficiency(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Эффективность', color: '#10B981', data: walk(mulberry32(9003), 1.38, 0.09, N, 2) },
    ],
  };
}

// ── Behavior ─────────────────────────────────────────────────────────────────

export function getBehaviorRumination(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Жвачка', color: '#3B82F6', data: walk(mulberry32(9101), 480, 35, N, 0) },
    ],
  };
}

export function getBehaviorActivity(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Активность', color: '#10B981', data: walk(mulberry32(9102), 68, 8, N, 0, 0, 100) },
    ],
  };
}

export function getBehaviorLying(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Лёжка', color: '#F59E0B', data: walk(mulberry32(9103), 11.2, 0.8, N, 1) },
    ],
  };
}

// ── Herd ─────────────────────────────────────────────────────────────────────

export function getHerdSize(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Поголовье', color: '#3B82F6', data: walk(mulberry32(9201), 240, 6, N, 0) },
    ],
  };
}

export function getHerdDimDistribution(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Свежие (0–60 ДДМ)',   color: '#3B82F6', data: walk(mulberry32(9202), 48,  4, N, 0) },
      { name: 'Средние (61–200 ДДМ)', color: '#10B981', data: walk(mulberry32(9203), 112, 7, N, 0) },
      { name: 'Поздние (201+ ДДМ)',   color: '#F59E0B', data: walk(mulberry32(9204), 80,  5, N, 0) },
    ],
  };
}

export function getHerdCalvings(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Отёлы', color: '#8B5CF6', data: walk(mulberry32(9205), 4.5, 2, N, 1, 0, 20) },
    ],
  };
}

// ── Weather ───────────────────────────────────────────────────────────────────

export function getWeatherThi(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'ТГИ', color: '#EF4444', data: walk(mulberry32(9301), 58, 12, N, 0, 20, 95) },
    ],
  };
}

export function getWeatherTemp(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Температура', color: '#F59E0B', data: walk(mulberry32(9302), 8, 6, N, 1, -15, 35) },
    ],
  };
}

export function getWeatherHumidity(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Влажность', color: '#3B82F6', data: walk(mulberry32(9303), 68, 10, N, 0, 20, 100) },
    ],
  };
}

// ── Finance ───────────────────────────────────────────────────────────────────

export function getFinanceRevenue(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Выручка', color: '#10B981', data: walk(mulberry32(9401), 12500, 800, N, 0) },
    ],
  };
}

export function getFinanceFeedCost(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Затраты на корм', color: '#EF4444', data: walk(mulberry32(9402), 4800, 350, N, 0) },
    ],
  };
}

export function getFinanceMargin(): AnalyticsData {
  return {
    labels: WEEK_LABELS,
    series: [
      { name: 'Маржа', color: '#3B82F6', data: walk(mulberry32(9403), 7700, 600, N, 0) },
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
