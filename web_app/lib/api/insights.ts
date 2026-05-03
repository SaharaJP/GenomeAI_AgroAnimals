export type InsightStatus = 'to_check' | 'to_follow_up' | 'done';
export type InsightSeverity = 'urgent' | 'high' | 'warn' | 'info';

export type InsightRecommendation = {
  id: string;
  text: string;
  deadline?: string;
};

export type InsightItem = {
  insight_id: string;
  type: string;
  severity: InsightSeverity;
  status: InsightStatus;
  date: string;
  animal_ids: string[];
  title: string;
  body: string;
  action: string;
  tags: string[];
  farmPct?: number;
  holdingPct?: number;
  chartData?: number[];
  chartLabel?: string;
  chartUnit?: string;
  recommendations?: InsightRecommendation[];
};

export const INSIGHT_STATUS_LABELS: Record<InsightStatus, string> = {
  to_check: 'К проверке',
  to_follow_up: 'В работе',
  done: 'Закрыто',
};

export const SEVERITY_BADGE: Record<InsightSeverity, string> = {
  urgent: 'badge-danger',
  high: 'badge-warning',
  warn: 'badge-warning',
  info: 'badge-info',
};

export const SEVERITY_LABEL: Record<InsightSeverity, string> = {
  urgent: 'Срочно',
  high: 'Высокий',
  warn: 'Предупреждение',
  info: 'Инфо',
};

export function formatRuDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

export const DEMO_INSIGHTS: InsightItem[] = [
  {
    insight_id: 'INS_001',
    type: 'health_alert',
    severity: 'urgent',
    status: 'to_check',
    date: '2026-04-21',
    animal_ids: ['3142'],
    title: 'Ночка: признаки мастита без назначенного лечения',
    body: 'Активность снизилась на 29% за 3 дня. СКК 450k, проводимость аномальная. Открытых протоколов лечения нет. По данным датчиков активности, корова провела на 4 часа меньше времени у кормушки за последние 48 часов.',
    action: 'Открыть карточку Ночки и назначить протокол мастита',
    tags: ['act4', 'mastitis_suspect', 'no_treatment'],
    farmPct: 28,
    holdingPct: 45,
    chartData: [100, 98, 95, 90, 85, 80, 75, 71],
    chartLabel: 'Активность (% от baseline)',
    chartUnit: '%',
    recommendations: [
      { id: 'r1', text: 'Проверить проводимость всех четвертей вымени', deadline: '2026-04-22' },
      { id: 'r2', text: 'Назначить протокол лечения мастита (Цефквин / Мастиет Форте)', deadline: '2026-04-22' },
      { id: 'r3', text: 'Внести в карантинный журнал, остановить сдачу молока на танк' },
    ],
  },
  {
    insight_id: 'INS_002',
    type: 'yield_drop_analysis',
    severity: 'high',
    status: 'to_check',
    date: '2026-04-21',
    animal_ids: ['4821'],
    title: 'Звёздочка: удой снизился на 22% после мастита и перевода',
    body: '3-я лактация, 156 DIM. Мастит выявлен 42 дня назад. Лечение Цефквином завершено. Перевод в группу 3 вызвал падение DMI на 14%, удой удерживается 28 кг/день (−22% от пика). Динамика не улучшается третью неделю подряд.',
    action: 'Оценить возможность возврата в группу 1 через 14 дней',
    tags: ['act2', 'yield_drop', 'mastitis_history'],
    farmPct: 35,
    holdingPct: 50,
    chartData: [36, 35, 34, 32, 30, 29, 28, 28],
    chartLabel: 'Удой (кг/день)',
    chartUnit: 'кг',
    recommendations: [
      { id: 'r1', text: 'Оценить DMI и поведение в группе 3 в течение 7 дней' },
      { id: 'r2', text: 'Рассмотреть возврат в группу 1 после стабилизации DMI', deadline: '2026-05-05' },
      { id: 'r3', text: 'Мониторить СКК еженедельно до достижения <200k' },
    ],
  },
  {
    insight_id: 'INS_003',
    type: 'culling_recommendation',
    severity: 'high',
    status: 'to_check',
    date: '2026-04-21',
    animal_ids: ['3891'],
    title: 'Малина: рекомендация — выбраковка',
    body: '285 DIM, 3-я лактация. 2 эпизода мастита за 60 дней. Open 145 дней. NPV последних 30 дней: −$180. Индекс выбраковки: 82/100. Прогноз по 4-й лактации — отрицательный при текущей динамике здоровья.',
    action: 'Принять решение о выбраковке или консервативном лечении',
    tags: ['act3', 'culling', 'negative_npv'],
    farmPct: 20,
    holdingPct: 40,
    chartData: [-80, -100, -130, -150, -160, -170, -175, -180],
    chartLabel: 'NPV 30 дней ($)',
    chartUnit: '$',
    recommendations: [
      { id: 'r1', text: 'Совещание с ветеринаром: оценить прогноз на 4-ю лактацию', deadline: '2026-04-25' },
      { id: 'r2', text: 'Если решение — выбраковка: запланировать в течение 14 дней' },
      { id: 'r3', text: 'Если оставить: назначить консервативный протокол с еженедельным КПЭ' },
    ],
  },
  {
    insight_id: 'INS_004',
    type: 'pregnancy_rate',
    severity: 'info',
    status: 'done',
    date: '2026-04-21',
    animal_ids: [],
    title: 'Индекс стельности 21d: 24% — уровень бенчмарка',
    body: 'Pregnancy Rate за последние 21 день: 24%. Целевой показатель: ≥22%. +2pp к прошлому месяцу. Синхронизация Ovsynch показала эффективность 89%. Ферма стабильно выше медианы второй квартал подряд.',
    action: 'Поддерживать текущий протокол синхронизации',
    tags: ['act1', 'kpi', 'repro'],
    farmPct: 80,
    holdingPct: 60,
    chartData: [19, 20, 21, 21, 22, 22, 23, 24],
    chartLabel: 'Pregnancy Rate 21D (%)',
    chartUnit: '%',
    recommendations: [
      { id: 'r1', text: 'Продолжать Ovsynch-протокол без изменений' },
      { id: 'r2', text: 'Поделиться результатом с директором как KPI успеха' },
    ],
  },
  {
    insight_id: 'INS_005',
    type: 'scc_trend',
    severity: 'warn',
    status: 'to_check',
    date: '2026-04-21',
    animal_ids: [],
    title: 'СКК в группе Лактирующие III растёт второй месяц',
    body: 'Среднее СКК PEN_LACT_3 выросло с 185k до 247k за 45 дней. 6 коров пересекли порог 400k. Если тренд сохранится, ферма рискует потерять молочный класс до конца квартала. Последняя ревизия оборудования — 4 месяца назад.',
    action: 'Провести ревизию доильного оборудования и гигиены',
    tags: ['scc', 'milk_quality', 'group'],
    farmPct: 38,
    holdingPct: 62,
    chartData: [185, 195, 205, 215, 225, 235, 242, 247],
    chartLabel: 'Среднее СКК (тыс/мл)',
    chartUnit: 'k',
    recommendations: [
      { id: 'r1', text: 'Провести технический аудит доильного оборудования', deadline: '2026-04-25' },
      { id: 'r2', text: 'Проверить гигиену вымени и преддоильную обработку' },
      { id: 'r3', text: 'Выявить 6 коров выше 400k и назначить индивидуальный мониторинг' },
    ],
  },
  {
    insight_id: 'INS_006',
    type: 'heat_detection',
    severity: 'info',
    status: 'to_follow_up',
    date: '2026-04-21',
    animal_ids: ['3067', '3112'],
    title: '2 коровы с высокой активностью охоты сегодня утром',
    body: '3067 (Лада, активность +140% vs baseline) и 3112 (Радуга, +128%). Обе коровы показывают классические поведенческие признаки. Оптимальное окно для осеменения — следующие 6–12 часов.',
    action: 'Запланировать осеменение в операторский worklist',
    tags: ['act5', 'heat_detection', 'repro'],
    farmPct: 75,
    holdingPct: 58,
    chartData: [100, 102, 108, 115, 125, 135, 140, 140],
    chartLabel: 'Активность охоты (% baseline)',
    chartUnit: '%',
    recommendations: [
      { id: 'r1', text: 'Запланировать осеменение Лады (3067) и Радуги (3112) сегодня', deadline: '2026-04-21' },
      { id: 'r2', text: 'Занести в worklist оператора' },
    ],
  },
  {
    insight_id: 'INS_007',
    type: 'withdrawal_compliance',
    severity: 'warn',
    status: 'to_check',
    date: '2026-04-21',
    animal_ids: ['3033', '3078', '3101'],
    title: '5 коров в карантине: молоко не сдаётся на танк',
    body: 'Withdrawal период активен: 3033 (-2д), 3078 (-1д), 3101 (-3д), 3155 (-5д), 3201 (-4д). Риск нарушения пищевой безопасности при случайном смешивании молока. Требуется ручная верификация у оператора.',
    action: 'Проверить дату снятия карантина у каждой',
    tags: ['withdrawal', 'compliance', 'milk_quality'],
    farmPct: 55,
    holdingPct: 48,
    chartData: [3, 3, 4, 4, 5, 5, 5, 5],
    chartLabel: 'Коров в карантине (шт)',
    chartUnit: 'шт',
    recommendations: [
      { id: 'r1', text: 'Уточнить дату снятия карантина у каждой из 5 коров' },
      { id: 'r2', text: 'Обновить статусы в системе после проверки', deadline: '2026-04-22' },
    ],
  },
  {
    insight_id: 'INS_008',
    type: 'economics',
    severity: 'info',
    status: 'done',
    date: '2026-04-21',
    animal_ids: [],
    title: 'Средний надой сегодня: 28.5 кг/гол — в плановом диапазоне',
    body: 'Фактический надой 28.5 кг/гол/день. Плановый: 28.0–30.0. Health index: 94%. Стоимость корма на 1 кг молока: $0.21 — в норме. Показатель стабилен 8-й день подряд.',
    action: 'Мониторинг без действий',
    tags: ['act1', 'kpi', 'milk_yield'],
    farmPct: 68,
    holdingPct: 58,
    chartData: [27.8, 28.0, 28.1, 28.3, 28.4, 28.5, 28.5, 28.5],
    chartLabel: 'Средний надой (кг/гол/день)',
    chartUnit: 'кг',
    recommendations: [
      { id: 'r1', text: 'Продолжать текущий режим кормления и доения' },
    ],
  },
  {
    insight_id: 'INS_009',
    type: 'benchmark',
    severity: 'info',
    status: 'to_follow_up',
    date: '2026-04-21',
    animal_ids: [],
    title: 'Ферма на 3pp выше медианы аналогов по Pregnancy Rate',
    body: 'PR 21d = 24% vs медиана аналогичных хозяйств 21%. Разница +3pp даёт +14 стельностей в квартал. Это эквивалентно $4,200 дополнительного дохода за квартал при текущей цене нетели.',
    action: 'Поделиться с директором как KPI успеха',
    tags: ['benchmark', 'repro', 'kpi'],
    farmPct: 82,
    holdingPct: 65,
    chartData: [20, 21, 21, 22, 22, 23, 23, 24],
    chartLabel: 'Pregnancy Rate 21D (%)',
    chartUnit: '%',
    recommendations: [
      { id: 'r1', text: 'Подготовить отчёт для директора с динамикой PR' },
      { id: 'r2', text: 'Сохранить текущий протокол синхронизации как best practice' },
    ],
  },
  {
    insight_id: 'INS_010',
    type: 'dim_group_analysis',
    severity: 'info',
    status: 'to_follow_up',
    date: '2026-04-21',
    animal_ids: [],
    title: 'Группа Fresh (DIM 1-30): 50 коров, кетоз у 3',
    body: '50 свежеотёлившихся коров. 3 с признаками субклинического кетоза (BHBA >1.2). Плановый скрининг сработал. При раннем выявлении вероятность успешного лечения — 92%. Рекомендуется корректировка рациона для всей fresh-группы.',
    action: 'Проверить протокол кормления fresh-группы',
    tags: ['ketosis', 'fresh_cow', 'dim_group'],
    farmPct: 68,
    holdingPct: 60,
    chartData: [1, 1, 2, 2, 2, 3, 3, 3],
    chartLabel: 'Кетоз (BHBA >1.2, коров)',
    chartUnit: 'шт',
    recommendations: [
      { id: 'r1', text: 'Назначить дополнительный скрининг для 3 коров с кетозом' },
      { id: 'r2', text: 'Проверить состав fresh-рациона на содержание пропиленгликоля' },
      { id: 'r3', text: 'Увеличить частоту BHBA-мониторинга до DIM 21', deadline: '2026-05-12' },
    ],
  },
  {
    insight_id: 'INS_011',
    type: 'upcoming_events',
    severity: 'info',
    status: 'done',
    date: '2026-04-21',
    animal_ids: [],
    title: 'Прогноз: 8 отёлов ожидается в течение 14 дней',
    body: '8 коров с расчётной датой отёла до 2026-05-05. Проверьте готовность родильного отделения. Особое внимание: корова 4102 (3-й отёл, высокий риск родового пареза — профилактика кальцием обязательна).',
    action: 'Подготовить родильное отделение, запас препаратов для fresh-протокола',
    tags: ['calving', 'planning'],
    farmPct: 70,
    holdingPct: 65,
    chartData: [2, 3, 4, 5, 6, 7, 7, 8],
    chartLabel: 'Ожидаемых отёлов (кумул.)',
    chartUnit: 'шт',
    recommendations: [
      { id: 'r1', text: 'Проверить родильное отделение на готовность к приёму', deadline: '2026-04-25' },
      { id: 'r2', text: 'Пополнить запас препаратов для fresh-протокола' },
      { id: 'r3', text: 'Назначить профилактику кальцием корове 4102' },
    ],
  },
  {
    insight_id: 'INS_012',
    type: 'feed_efficiency',
    severity: 'warn',
    status: 'to_follow_up',
    date: '2026-04-21',
    animal_ids: [],
    title: 'DMI PEN_LACT_3 снизился на 8% за неделю',
    body: 'Группа Лактирующие III: средний DMI 20.1 кг vs 21.8 кг прошлой недели (−8%). Связано с переводом 3 коров после лечения. При продолжении тренда возможно снижение удоя на 5–7% в следующие 10 дней.',
    action: 'Проверить качество корма и провести подгонку рациона',
    tags: ['feed', 'dmi', 'group'],
    farmPct: 42,
    holdingPct: 62,
    chartData: [21.8, 21.5, 21.2, 20.9, 20.6, 20.3, 20.1, 20.1],
    chartLabel: 'Средний DMI группы (кг)',
    chartUnit: 'кг',
    recommendations: [
      { id: 'r1', text: 'Проверить качество TMR в группе Лактирующие III' },
      { id: 'r2', text: 'Оценить адаптацию 3 переведённых коров к новому рациону' },
      { id: 'r3', text: 'Скорректировать рацион при сохранении тренда > 5 дней', deadline: '2026-04-27' },
    ],
  },
];
