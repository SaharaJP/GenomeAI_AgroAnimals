export type TimelineEvent = {
  timeline_event_id: string;
  date: string;
  event_type: string;
  title: string;
  body: string;
  source?: string;
  has_impact: boolean;
};

export type MetricWindow = '3d' | '1w' | '2w' | '4w';

export type MetricComparison = {
  metric_id: string;
  label: string;
  unit: string;
  before_value: number;
  after_value: number;
  higher_is_better: boolean;
  max_display?: number;
  // Statistical fields — present when data comes from /api/impact
  welch_t_pvalue?: number;
  bootstrap_ci_95?: [number, number];
  significance?: 'significant' | 'not_significant' | 'inconclusive';
  effect_magnitude?: 'negligible' | 'small' | 'medium' | 'large';
};

export type OtherChange = {
  metric: string;
  before: number | string;
  after: number | string;
  delta_label: string;
  direction: 'up' | 'down' | 'neutral';
};

export type ImpactWindowData = {
  before_period: { start: string; end: string };
  after_period: { start: string; end: string };
  metrics: MetricComparison[];
  other_changes: OtherChange[];
};

export type ImpactAnalysis = {
  event_id: string;
  windows: Record<MetricWindow, ImpactWindowData>;
};

export const TIMELINE_EVENT_ICONS: Record<string, string> = {
  ration_change: 'Salad',
  new_employee: 'UserPlus',
  feeding_schedule: 'Salad',
  hoof_trim: 'Scissors',
  pen_density: 'Users',
  bedding: 'Package',
  mastitis_outbreak: 'FlaskConical',
  mastitis_recurrence: 'FlaskConical',
  pen_move: 'ArrowRightLeft',
  vaccination: 'Syringe',
  breeding: 'Heart',
  heat_detection: 'Heart',
  calving_wave: 'Baby',
  scc_alert: 'AlertCircle',
  scc_group_rise: 'TrendingUp',
  withdrawal_compliance: 'ShieldCheck',
  benchmark_update: 'Award',
  daily_kpi_snapshot: 'BarChart3',
  activity_drop: 'TrendingDown',
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  ration_change: 'Смена рациона',
  new_employee: 'Новый сотрудник',
  feeding_schedule: 'График кормления',
  hoof_trim: 'Обрезка копыт',
  pen_density: 'Плотность в пенне',
  bedding: 'Подстилка',
  mastitis_outbreak: 'Мастит',
  mastitis_recurrence: 'Мастит (повтор)',
  pen_move: 'Перевод',
  vaccination: 'Вакцинация',
  breeding: 'Осеменение',
  heat_detection: 'Охота',
  calving_wave: 'Отёл',
  scc_alert: 'Сигнал СКК',
  scc_group_rise: 'Рост СКК',
  withdrawal_compliance: 'Карантин',
  benchmark_update: 'Бенчмарк',
  daily_kpi_snapshot: 'Снапшот KPI',
  activity_drop: 'Падение активности',
};

export const DEMO_TIMELINE_EVENTS: TimelineEvent[] = [
  {
    timeline_event_id: 'DEMO_001',
    date: '2026-03-11',
    event_type: 'ration_change',
    title: 'Смена рациона — добавлено Ezfeed',
    body: 'Несколько изменений рецептуры: затронуты пенны 1, 12, 2. Детали рецепта в ПО кормления.',
    source: 'Автоматически добавлено вашим ПО кормления',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_002',
    date: '2026-03-06',
    event_type: 'new_employee',
    title: 'Новый сотрудник на доильном зале',
    body: 'Новый оператор прошёл обучение и приступил к работе в доильном зале.',
    source: 'Добавлено вручную',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_003',
    date: '2026-02-25',
    event_type: 'feeding_schedule',
    title: 'График кормления — Dry Cows pen',
    body: 'Скорректирован режим кормления для сухостойных коров: +0.5 кг СВ, 4 раза в день.',
    source: 'Добавлено вручную',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_004',
    date: '2026-02-19',
    event_type: 'ration_change',
    title: 'Смена рациона для пенна 7',
    body: 'Рацион TMR скорректирован для группы 7: снижена доля кукурузного силоса на 15%.',
    source: 'Автоматически добавлено вашим ПО кормления',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_005',
    date: '2026-02-15',
    event_type: 'ration_change',
    title: 'Возврат к кукурузе высокой влажности',
    body: 'После 3-недельного перерыва группа 1 перешла обратно на HMSC. DMI должен стабилизироваться за 7 дней.',
    source: 'Добавлено вручную',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_006',
    date: '2026-02-07',
    event_type: 'hoof_trim',
    title: 'Обрезка копыт — весь пенн',
    body: 'Плановая обрезка копыт для всего стада: 68 коров за 2 дня. Результаты в карточках животных.',
    source: 'Добавлено вручную',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_007',
    date: '2026-01-25',
    event_type: 'pen_density',
    title: 'Плотность в Close-up пенне',
    body: 'Высокая стельность: плотность в Close-up выросла до 118%. Требуется расширение группы.',
    source: 'Добавлено вручную',
    has_impact: true,
  },
  {
    timeline_event_id: 'DEMO_008',
    date: '2026-01-17',
    event_type: 'bedding',
    title: 'Новая подстилка для группы 3',
    body: 'Переход с опилок на резиновые маты в боксах группы 3. Период адаптации 5-7 дней.',
    source: 'Добавлено вручную',
    has_impact: true,
  },
];

const IMPACT_DEMO_001: ImpactAnalysis = {
  event_id: 'DEMO_001',
  windows: {
    '3d': {
      before_period: { start: '08.03.2026', end: '11.03.2026' },
      after_period: { start: '11.03.2026', end: '14.03.2026' },
      metrics: [
        {
          metric_id: 'dmi_per_group',
          label: 'DMI per group',
          unit: 'кг',
          before_value: 19.5,
          after_value: 18.4,
          higher_is_better: true,
          max_display: 25,
        },
        {
          metric_id: 'eating_time',
          label: 'Время поедания в день, per pen',
          unit: 'мин',
          before_value: 414,
          after_value: 419,
          higher_is_better: true,
          max_display: 500,
        },
        {
          metric_id: 'ecm_yield',
          label: 'ECM yield per cow per pen',
          unit: 'кг',
          before_value: 26.5,
          after_value: 26.7,
          higher_is_better: true,
          max_display: 35,
        },
        {
          metric_id: 'milk_yield',
          label: 'Avg Milk Yield per cow, per pen',
          unit: 'кг',
          before_value: 35.5,
          after_value: 34.5,
          higher_is_better: true,
          max_display: 45,
        },
        {
          metric_id: 'rumination',
          label: 'Время руминации per pen, per day',
          unit: 'мин',
          before_value: 474,
          after_value: 488,
          higher_is_better: true,
          max_display: 550,
        },
      ],
      other_changes: [
        {
          metric: 'Temperature Humidity Index (THI)',
          before: 48,
          after: 50,
          delta_label: '↑ 2',
          direction: 'up',
        },
      ],
    },
    '1w': {
      before_period: { start: '04.03.2026', end: '11.03.2026' },
      after_period: { start: '11.03.2026', end: '18.03.2026' },
      metrics: [
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 19.8, after_value: 19.2, higher_is_better: true, max_display: 25 },
        { metric_id: 'eating_time', label: 'Время поедания в день, per pen', unit: 'мин', before_value: 412, after_value: 416, higher_is_better: true, max_display: 500 },
        { metric_id: 'ecm_yield', label: 'ECM yield per cow per pen', unit: 'кг', before_value: 26.3, after_value: 26.6, higher_is_better: true, max_display: 35 },
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.7, after_value: 34.9, higher_is_better: true, max_display: 45 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 472, after_value: 480, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Temperature Humidity Index (THI)', before: 47, after: 50, delta_label: '↑ 3', direction: 'up' },
        { metric: 'Lying time per cow, per day', before: '11.2 ч', after: '11.6 ч', delta_label: '↑ 24 мин', direction: 'up' },
      ],
    },
    '2w': {
      before_period: { start: '25.02.2026', end: '11.03.2026' },
      after_period: { start: '11.03.2026', end: '25.03.2026' },
      metrics: [
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 19.9, after_value: 19.5, higher_is_better: true, max_display: 25 },
        { metric_id: 'eating_time', label: 'Время поедания в день, per pen', unit: 'мин', before_value: 411, after_value: 417, higher_is_better: true, max_display: 500 },
        { metric_id: 'ecm_yield', label: 'ECM yield per cow per pen', unit: 'кг', before_value: 26.2, after_value: 26.8, higher_is_better: true, max_display: 35 },
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.6, after_value: 35.0, higher_is_better: true, max_display: 45 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 470, after_value: 482, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Temperature Humidity Index (THI)', before: 46, after: 51, delta_label: '↑ 5', direction: 'up' },
        { metric: 'SCC group average', before: '185k', after: '178k', delta_label: '↓ 7k', direction: 'down' },
      ],
    },
    '4w': {
      before_period: { start: '11.02.2026', end: '11.03.2026' },
      after_period: { start: '11.03.2026', end: '08.04.2026' },
      metrics: [
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 20.1, after_value: 19.8, higher_is_better: true, max_display: 25 },
        { metric_id: 'eating_time', label: 'Время поедания в день, per pen', unit: 'мин', before_value: 410, after_value: 418, higher_is_better: true, max_display: 500 },
        { metric_id: 'ecm_yield', label: 'ECM yield per cow per pen', unit: 'кг', before_value: 26.0, after_value: 27.1, higher_is_better: true, max_display: 35 },
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.4, after_value: 35.2, higher_is_better: true, max_display: 45 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 468, after_value: 479, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Temperature Humidity Index (THI)', before: 44, after: 52, delta_label: '↑ 8', direction: 'up' },
        { metric: 'SCC group average', before: '188k', after: '174k', delta_label: '↓ 14k', direction: 'down' },
        { metric: 'Feed cost per cow per day', before: '142 р', after: '148 р', delta_label: '↑ 6 р', direction: 'up' },
      ],
    },
  },
};

const IMPACT_DEMO_002: ImpactAnalysis = {
  event_id: 'DEMO_002',
  windows: {
    '3d': {
      before_period: { start: '03.03.2026', end: '06.03.2026' },
      after_period: { start: '06.03.2026', end: '09.03.2026' },
      metrics: [
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.8, after_value: 35.2, higher_is_better: true, max_display: 45 },
        { metric_id: 'milking_duration', label: 'Длительность доения per cow', unit: 'мин', before_value: 6.8, after_value: 7.4, higher_is_better: false, max_display: 10 },
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 20.1, after_value: 19.9, higher_is_better: true, max_display: 25 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 478, after_value: 471, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Скорость выхода из зала (коров/час)', before: 62, after: 58, delta_label: '↓ 4', direction: 'down' },
      ],
    },
    '1w': {
      before_period: { start: '27.02.2026', end: '06.03.2026' },
      after_period: { start: '06.03.2026', end: '13.03.2026' },
      metrics: [
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.9, after_value: 35.4, higher_is_better: true, max_display: 45 },
        { metric_id: 'milking_duration', label: 'Длительность доения per cow', unit: 'мин', before_value: 6.7, after_value: 7.2, higher_is_better: false, max_display: 10 },
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 20.2, after_value: 20.0, higher_is_better: true, max_display: 25 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 479, after_value: 475, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Скорость выхода из зала (коров/час)', before: 63, after: 59, delta_label: '↓ 4', direction: 'down' },
      ],
    },
    '2w': {
      before_period: { start: '20.02.2026', end: '06.03.2026' },
      after_period: { start: '06.03.2026', end: '20.03.2026' },
      metrics: [
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.8, after_value: 35.6, higher_is_better: true, max_display: 45 },
        { metric_id: 'milking_duration', label: 'Длительность доения per cow', unit: 'мин', before_value: 6.7, after_value: 7.0, higher_is_better: false, max_display: 10 },
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 20.1, after_value: 20.1, higher_is_better: true, max_display: 25 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 477, after_value: 476, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Скорость выхода из зала (коров/час)', before: 62, after: 61, delta_label: '↓ 1', direction: 'down' },
      ],
    },
    '4w': {
      before_period: { start: '06.02.2026', end: '06.03.2026' },
      after_period: { start: '06.03.2026', end: '03.04.2026' },
      metrics: [
        { metric_id: 'milk_yield', label: 'Avg Milk Yield per cow, per pen', unit: 'кг', before_value: 35.7, after_value: 35.8, higher_is_better: true, max_display: 45 },
        { metric_id: 'milking_duration', label: 'Длительность доения per cow', unit: 'мин', before_value: 6.8, after_value: 6.8, higher_is_better: false, max_display: 10 },
        { metric_id: 'dmi_per_group', label: 'DMI per group', unit: 'кг', before_value: 20.0, after_value: 20.2, higher_is_better: true, max_display: 25 },
        { metric_id: 'rumination', label: 'Время руминации per pen, per day', unit: 'мин', before_value: 476, after_value: 478, higher_is_better: true, max_display: 550 },
      ],
      other_changes: [
        { metric: 'Скорость выхода из зала (коров/час)', before: 62, after: 62, delta_label: '→ 0', direction: 'neutral' },
      ],
    },
  },
};

export const DEMO_IMPACT_ANALYSES: Record<string, ImpactAnalysis> = {
  DEMO_001: IMPACT_DEMO_001,
  DEMO_002: IMPACT_DEMO_002,
};

export function getImpactForEvent(eventId: string, window: MetricWindow): ImpactWindowData | null {
  const analysis = DEMO_IMPACT_ANALYSES[eventId];
  if (!analysis) return null;
  return analysis.windows[window] ?? null;
}

// ---------------------------------------------------------------------------
// Real API fetch — replaces mock in impact panel
// ---------------------------------------------------------------------------

type KpiImpactResult = {
  kpi: string;
  welch_t_pvalue: number;
  cohen_d_effect_size: number;
  bootstrap_ci_95: [number, number];
  significance: 'significant' | 'not_significant' | 'inconclusive';
  effect_magnitude: 'negligible' | 'small' | 'medium' | 'large';
  diff_in_diff_effect: number;
  treated_before: number;
  treated_after: number;
  sample_sizes: { treated: number; control: number };
};

type ImpactApiResponse = {
  event_id: string;
  farm_id: string;
  window: string;
  results: KpiImpactResult[];
  demo_mode: boolean;
};

const KPI_META: Record<string, { label: string; unit: string; higher_is_better: boolean; max_display: number }> = {
  milk_yield:       { label: 'Avg Milk Yield per cow, per pen', unit: 'кг',  higher_is_better: true,  max_display: 45 },
  dmi_per_group:    { label: 'DMI per group',                   unit: 'кг',  higher_is_better: true,  max_display: 25 },
  eating_time:      { label: 'Время поедания в день, per pen',  unit: 'мин', higher_is_better: true,  max_display: 500 },
  rumination:       { label: 'Время руминации per pen, per day',unit: 'мин', higher_is_better: true,  max_display: 550 },
  ecm_yield:        { label: 'ECM yield per cow per pen',       unit: 'кг',  higher_is_better: true,  max_display: 35 },
  milking_duration: { label: 'Длительность доения per cow',     unit: 'мин', higher_is_better: false, max_display: 10 },
};

function _windowPeriods(eventDate: string, w: MetricWindow): { before: { start: string; end: string }; after: { start: string; end: string } } {
  const days = { '3d': 3, '1w': 7, '2w': 14, '4w': 28 }[w];
  const ev = new Date(eventDate);
  const beforeStart = new Date(ev); beforeStart.setDate(ev.getDate() - days);
  const afterEnd   = new Date(ev); afterEnd.setDate(ev.getDate() + days);
  const fmt = (d: Date) => d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }).replace(/\//g, '.');
  return {
    before: { start: fmt(beforeStart), end: fmt(ev) },
    after:  { start: fmt(ev),          end: fmt(afterEnd) },
  };
}

export async function fetchImpactForEvent(
  event: TimelineEvent,
  window: MetricWindow,
  kpiList: string[] = ['milk_yield', 'dmi_per_group', 'eating_time', 'rumination'],
): Promise<ImpactWindowData | null> {
  try {
    const resp = await fetch('/api/impact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_id: event.timeline_event_id,
        farm_id: 'demo-farm-v1',
        kpi_list: kpiList,
        window,
      }),
    });
    if (!resp.ok) return null;
    const data: ImpactApiResponse = await resp.json();

    const periods = _windowPeriods(event.date, window);
    const metrics: MetricComparison[] = data.results.map((r) => {
      const meta = KPI_META[r.kpi] ?? { label: r.kpi, unit: '', higher_is_better: true, max_display: 100 };
      return {
        metric_id: r.kpi,
        label: meta.label,
        unit: meta.unit,
        before_value: r.treated_before,
        after_value: r.treated_after,
        higher_is_better: meta.higher_is_better,
        max_display: meta.max_display,
        welch_t_pvalue: r.welch_t_pvalue,
        bootstrap_ci_95: r.bootstrap_ci_95,
        significance: r.significance,
        effect_magnitude: r.effect_magnitude,
      };
    });

    return {
      before_period: periods.before,
      after_period: periods.after,
      metrics,
      other_changes: [],
    };
  } catch {
    return null;
  }
}

export function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date('2026-04-23');
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'сегодня';
  if (diffDays === 1) return 'вчера';
  if (diffDays < 7) return `${diffDays} дней назад`;
  if (diffDays < 14) return 'неделю назад';
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} нед. назад`;
  if (diffDays < 60) return 'месяц назад';
  return `${Math.floor(diffDays / 30)} мес. назад`;
}

export function formatDayMonth(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function formatMonthYear(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { month: 'short', year: 'numeric' });
}

export function groupEventsByMonth(events: TimelineEvent[]): Map<string, TimelineEvent[]> {
  const map = new Map<string, TimelineEvent[]>();
  for (const ev of events) {
    const key = formatMonthYear(ev.date);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(ev);
  }
  return map;
}
