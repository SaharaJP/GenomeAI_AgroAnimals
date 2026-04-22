export type OverviewInsight = {
  insight_id: string;
  type: string;
  severity: 'urgent' | 'high' | 'medium' | 'low';
  date: string;
  title: string;
  body: string;
  action: string;
  tags: string[];
  farmPct?: number;
  holdingPct?: number;
};

export type OverviewTimelineEvent = {
  timeline_event_id: string;
  date: string;
  event_type: string;
  title: string;
  body: string;
  impact?: string | null;
  impact_value?: string | null;
};

export type DashboardMetric = {
  id: string;
  headerLabel: string;
  subtitle: string;
  chartData: number[];
  xLabels: string[];
  unit: string;
};

export const DEMO_INSIGHTS: OverviewInsight[] = [
  {
    insight_id: 'INS_001',
    type: 'health_alert',
    severity: 'urgent',
    date: '2026-04-21',
    title: 'Ночка: признаки мастита без назначенного лечения',
    body: 'Активность снизилась на 29% за 3 дня. СКК 450k, проводимость аномальная. Открытых протоколов лечения нет.',
    action: 'Открыть карточку Ночки и назначить протокол мастита',
    tags: ['act4', 'mastitis_suspect'],
    farmPct: 72,
    holdingPct: 48,
  },
  {
    insight_id: 'INS_002',
    type: 'yield_drop_analysis',
    severity: 'high',
    date: '2026-04-21',
    title: 'Звёздочка: удой снизился на 22% после мастита и перевода',
    body: '3-я лактация, 156 DIM. Мастит выявлен 42 дня назад. Лечение Цефквином завершено. Перевод в группу 3 вызвал падение DMI на 14%, удой удерживается 28 кг/день (−22%).',
    action: 'Оценить возможность возврата в группу 1 через 14 дней',
    tags: ['act2', 'yield_drop'],
    farmPct: 65,
    holdingPct: 50,
  },
  {
    insight_id: 'INS_003',
    type: 'culling_recommendation',
    severity: 'high',
    date: '2026-04-21',
    title: 'Малина: рекомендация — выбраковка',
    body: '285 DIM, 3-я лактация. 2 эпизода мастита за 60 дней. Open 145 дней. NPV последних 30 дней: −$180. Индекс выбраковки: 82/100.',
    action: 'Принять решение о выбраковке или консервативном лечении',
    tags: ['act3', 'culling'],
    farmPct: 45,
    holdingPct: 55,
  },
  {
    insight_id: 'INS_004',
    type: 'pregnancy_rate',
    severity: 'medium',
    date: '2026-04-14',
    title: 'Стельность 21D: 24% — выше среднего по холдингу',
    body: 'За последние 21 день confirmed pregnancy rate 24% при среднем по холдингу 21%. Синхронизация Ovsynch показала эффективность 89%.',
    action: 'Продолжить текущий протокол синхронизации',
    tags: ['reproduction', 'above_average'],
    farmPct: 80,
    holdingPct: 58,
  },
  {
    insight_id: 'INS_005',
    type: 'milk_quality',
    severity: 'low',
    date: '2026-04-10',
    title: 'Жир/белок в норме: 3.8% / 3.1% по стаду',
    body: 'Средние показатели за апрель соответствуют плановым значениям. Отклонений по группам нет.',
    action: 'Следить за динамикой в переходный период',
    tags: ['milk_quality', 'on_target'],
    farmPct: 60,
    holdingPct: 62,
  },
];

export const DEMO_TIMELINE_EVENTS: OverviewTimelineEvent[] = [
  {
    timeline_event_id: 'TL_001',
    date: '2026-04-10',
    event_type: 'mastitis_outbreak',
    title: 'Мастит у Звёздочки — начало лечения',
    body: 'СКК 450k, проводимость аномальная. Начат протокол Цефквином.',
    impact: 'yield_loss',
    impact_value: '−22% удоя на 28 дней',
  },
  {
    timeline_event_id: 'TL_002',
    date: '2026-04-14',
    event_type: 'pen_move',
    title: 'Звёздочка переведена в группу 3',
    body: 'Социальный стресс после лечения. DMI −14%.',
    impact: 'dmi_drop',
    impact_value: '−14% DMI на 10 дней',
  },
  {
    timeline_event_id: 'TL_003',
    date: '2026-03-11',
    event_type: 'ration_change',
    title: 'Рацион изменён — добавлен E/feed',
    body: 'Несколько изменений рецептуры: затронуты группы 1, 12, 2. Детали рецепта в ПО кормления.',
    impact: null,
    impact_value: null,
  },
  {
    timeline_event_id: 'TL_004',
    date: '2026-03-06',
    event_type: 'new_employee',
    title: 'Новый оператор на доильном parlour',
    body: 'Новый сотрудник прошёл обучение и приступил к работе.',
    impact: null,
    impact_value: null,
  },
  {
    timeline_event_id: 'TL_005',
    date: '2026-02-20',
    event_type: 'mastitis_recurrence',
    title: 'Малина: первый эпизод мастита',
    body: 'Задняя правая четверть. СКК 680k. Эпизод 1 из 2.',
    impact: 'yield_loss',
    impact_value: '−30% удоя на 7 дней',
  },
  {
    timeline_event_id: 'TL_006',
    date: '2026-02-14',
    event_type: 'feeding_schedule',
    title: 'Изменение рецептуры кормления',
    body: 'Рецепт TMR скорректирован: +0.5 кг СВ для лактирующих группы 1.',
    impact: 'feed_cost',
    impact_value: '+3.2% стоимость корма',
  },
];

export const EVENT_TYPE_LABELS: Record<string, string> = {
  mastitis_outbreak: 'Мастит',
  mastitis_recurrence: 'Мастит (повтор)',
  pen_move: 'Перевод',
  new_employee: 'Сотрудник',
  feeding_schedule: 'Кормление',
  vaccination: 'Вакцинация',
  ration_change: 'Рацион',
  breeding: 'Осеменение',
};

export const DASHBOARD_METRICS: DashboardMetric[] = [
  {
    id: 'dmi_lactating',
    headerLabel: 'Ваша панель',
    subtitle: 'DMI на корову для лактирующих',
    chartData: [21.2, 22.0, 22.5, 23.1, 23.8, 24.2, 25.0, 25.5, 26.1, 26.8,
                27.2, 27.8, 28.5, 28.9, 29.4, 29.8, 30.2, 30.6, 31.0, 31.5,
                31.8, 32.2, 32.5, 32.8, 33.0, 33.4, 33.8, 34.1, 34.5, 34.8],
    xLabels: ['27.01', '14.03', '03.05'],
    unit: 'кг/д',
  },
  {
    id: 'milk_yield',
    headerLabel: 'Ваша панель',
    subtitle: 'Средний удой по стаду',
    chartData: [26.8, 27.2, 27.5, 27.9, 28.3, 28.6, 28.9, 29.2, 29.5, 29.8,
                30.0, 30.3, 30.6, 30.8, 31.1, 31.3, 31.6, 31.8, 32.0, 32.2,
                32.4, 32.6, 32.8, 33.0, 33.2, 33.4, 33.6, 33.8, 34.0, 34.2],
    xLabels: ['27.01', '14.03', '03.05'],
    unit: 'кг',
  },
  {
    id: 'pregnancy_rate',
    headerLabel: 'Ваша панель',
    subtitle: 'Индекс стельности 21D',
    chartData: [19.5, 20.2, 20.8, 21.3, 21.8, 22.2, 22.6, 23.0, 23.4, 23.7,
                24.0, 24.3, 24.6, 24.8, 25.0, 25.2, 25.4, 25.6, 25.8, 26.0,
                26.2, 26.4, 26.6, 26.8, 27.0, 27.2, 27.4, 27.6, 27.8, 28.0],
    xLabels: ['27.01', '14.03', '03.05'],
    unit: '%',
  },
];
