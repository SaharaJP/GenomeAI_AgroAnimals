'use client';

export type EventTypeOption = {
  value: string;
  label: string;
  emoji: string;
  placeholder: string;
};

export const EVENT_TYPE_OPTIONS: EventTypeOption[] = [
  { value: 'ration_change',    label: 'Смена рациона',       emoji: '🌾', placeholder: 'Добавление новой добавки в рацион' },
  { value: 'pen_move',         label: 'Перевод группы',      emoji: '🏡', placeholder: 'Перевод коров между группами' },
  { value: 'new_employee',     label: 'Новый сотрудник',     emoji: '👤', placeholder: 'Новый оператор в доильном зале' },
  { value: 'feeding_schedule', label: 'График кормления',    emoji: '🍽', placeholder: 'Изменение режима кормления' },
  { value: 'hoof_trim',        label: 'Обработка копыт',     emoji: '🦶', placeholder: 'Плановая обрезка копыт' },
  { value: 'vaccination',      label: 'Вакцинация',          emoji: '💉', placeholder: 'Вакцинация против...' },
  { value: 'bedding',          label: 'Смена подстилки',     emoji: '🧹', placeholder: 'Смена подстилки в группе...' },
  { value: 'pen_density',      label: 'Изм. плотности',      emoji: '📐', placeholder: 'Изменение плотности в группе...' },
  { value: 'lab_tests',        label: 'Лаб. тесты',          emoji: '🔬', placeholder: 'Лабораторные тесты...' },
  { value: 'other',            label: 'Другое',              emoji: '📋', placeholder: 'Опишите событие...' },
];

interface Props {
  value: string;
  onChange: (val: string) => void;
}

export function EventTypeSelect({ value, onChange }: Props) {
  return (
    <div className="ae-type-grid">
      {EVENT_TYPE_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`ae-type-btn${value === opt.value ? ' ae-type-btn--active' : ''}`}
          onClick={() => onChange(opt.value)}
        >
          <span className="ae-type-emoji">{opt.emoji}</span>
          <span className="ae-type-label">{opt.label}</span>
        </button>
      ))}
    </div>
  );
}
