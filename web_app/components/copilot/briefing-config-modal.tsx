'use client';

import { useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { Card } from '@/components/ui/card';
import { CreateBriefCard } from '@/components/copilot/create-brief-card';
import { SettingsCard } from '@/components/copilot/settings-card';

export type BriefingSchedule = {
  periodicity: 'daily' | 'weekly' | 'monthly';
  timeOfDay: string;
  autoCreateTasks: boolean;
};

export const DEFAULT_BRIEFING_SCHEDULE: BriefingSchedule = {
  periodicity: 'weekly',
  timeOfDay: '07:00',
  autoCreateTasks: false,
};

export const BRIEFING_PERIOD_LABELS: Record<BriefingSchedule['periodicity'], string> = {
  daily: 'Каждый день',
  weekly: 'Каждую неделю',
  monthly: 'Каждый месяц',
};

type Props = {
  open: boolean;
  onClose: () => void;
  dateStart: string;
  dateEnd: string;
  onDateStartChange: (v: string) => void;
  onDateEndChange: (v: string) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  weeklyEmailEnabled: boolean;
  onToggleWeeklyEmail: (v: boolean) => void;
  schedule: BriefingSchedule;
  onScheduleChange: (next: BriefingSchedule) => void;
  onSaveSchedule: () => void;
};

export function BriefingConfigModal({
  open,
  onClose,
  dateStart,
  dateEnd,
  onDateStartChange,
  onDateEndChange,
  onGenerate,
  isGenerating,
  weeklyEmailEnabled,
  onToggleWeeklyEmail,
  schedule,
  onScheduleChange,
  onSaveSchedule,
}: Props) {
  return (
    <Modal open={open} onClose={onClose} title="Настройка брифинга" width={680}>
      <CreateBriefCard
        dateStart={dateStart}
        dateEnd={dateEnd}
        onDateStartChange={onDateStartChange}
        onDateEndChange={onDateEndChange}
        onSubmit={onGenerate}
        isLoading={isGenerating}
      />
      <SettingsCard enabled={weeklyEmailEnabled} onToggle={onToggleWeeklyEmail} />
      <ScheduleCard schedule={schedule} onChange={onScheduleChange} onSave={onSaveSchedule} />
    </Modal>
  );
}

type ScheduleCardProps = {
  schedule: BriefingSchedule;
  onChange: (next: BriefingSchedule) => void;
  onSave: () => void;
};

function ScheduleCard({ schedule, onChange, onSave }: ScheduleCardProps) {
  const [savedFlash, setSavedFlash] = useState(false);

  function handleSave() {
    onSave();
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 1500);
  }

  return (
    <Card>
      <h2 className="card-title">Расписание и автозадачи</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Периодичность</span>
          <select
            value={schedule.periodicity}
            onChange={(e) =>
              onChange({ ...schedule, periodicity: e.target.value as BriefingSchedule['periodicity'] })
            }
            className="input"
            style={{ maxWidth: 240 }}
          >
            {(Object.keys(BRIEFING_PERIOD_LABELS) as BriefingSchedule['periodicity'][]).map((p) => (
              <option key={p} value={p}>{BRIEFING_PERIOD_LABELS[p]}</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Время формирования</span>
          <input
            type="time"
            value={schedule.timeOfDay}
            onChange={(e) => onChange({ ...schedule, timeOfDay: e.target.value })}
            className="input"
            style={{ maxWidth: 240 }}
          />
        </label>

        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            cursor: 'pointer',
            userSelect: 'none',
          }}
        >
          <span style={{ position: 'relative', display: 'inline-block', width: 38, height: 22, flexShrink: 0 }}>
            <input
              type="checkbox"
              checked={schedule.autoCreateTasks}
              onChange={(e) => onChange({ ...schedule, autoCreateTasks: e.target.checked })}
              style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
              aria-label="Автоматическая постановка задач по брифингу"
            />
            <span
              style={{
                position: 'absolute',
                inset: 0,
                background: schedule.autoCreateTasks ? 'var(--accent)' : '#d1d5db',
                borderRadius: 11,
                transition: 'background 0.2s ease',
              }}
            />
            <span
              style={{
                position: 'absolute',
                left: schedule.autoCreateTasks ? 18 : 2,
                top: 3,
                width: 16,
                height: 16,
                background: 'white',
                borderRadius: '50%',
                transition: 'left 0.2s ease',
                boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
              }}
            />
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55 }}>
            Автоматически создавать задачи по итогам брифинга (иначе — требуют согласования)
          </span>
        </label>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            className="button button-primary"
            onClick={handleSave}
          >
            Сохранить расписание
          </button>
          {savedFlash && (
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              Сохранено локально. Подключение к бэкенду — следующий шаг (P1-1b).
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}
