'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { Settings, History } from 'lucide-react';
import { MorningBriefCard } from '@/components/overview/morning-brief-card';
import {
  BriefingConfigModal,
  DEFAULT_BRIEFING_SCHEDULE,
  type BriefingSchedule,
} from '@/components/copilot/briefing-config-modal';
import { BriefingHistoryModal } from '@/components/copilot/briefing-history-modal';
import { getAllSeededBriefs, getSeededBrief } from '@/lib/weekly-briefs';
import type { WeeklyBrief } from '@/lib/weekly-briefs';
import { pathLabels } from '@/lib/navigation';

const BriefPreview = dynamic(
  () => import('@/components/copilot/brief-preview').then((m) => m.BriefPreview),
  {
    loading: () => (
      <div className="card" style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
        Загружаю брифинг…
      </div>
    ),
    ssr: false,
  },
);

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function weekAgoStr(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

export default function DailySummaryPage() {
  const [configOpen, setConfigOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const [dateStart, setDateStart] = useState<string>(weekAgoStr());
  const [dateEnd, setDateEnd] = useState<string>(todayStr());
  const [generatedBrief, setGeneratedBrief] = useState<WeeklyBrief | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [weeklyEmailEnabled, setWeeklyEmailEnabled] = useState(false);
  const [schedule, setSchedule] = useState<BriefingSchedule>(DEFAULT_BRIEFING_SCHEDULE);
  const [toast, setToast] = useState<string | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  async function handleGenerate() {
    setIsGenerating(true);
    setGeneratedBrief(null);
    try {
      const res = await fetch('/api/ai/weekly-brief', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_start: dateStart, week_end: dateEnd }),
      });
      if (res.ok) {
        setGeneratedBrief((await res.json()) as WeeklyBrief);
      } else {
        setGeneratedBrief(getSeededBrief());
      }
    } catch {
      setGeneratedBrief(getSeededBrief());
    }
    setIsGenerating(false);
    setConfigOpen(false);
    setTimeout(
      () => document.getElementById('brief-preview')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      50,
    );
  }

  function handleSaveSchedule() {
    showToast('Расписание сохранено локально. Подключение к бэкенду — P1-1b.');
  }

  return (
    <div className="grid">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <h1 className="page-title">{pathLabels['/daily-summary']}</h1>
          <p className="page-subtitle">Ежедневная сводка фермы и связанные действия.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="button"
            onClick={() => setConfigOpen(true)}
          >
            <Settings size={14} strokeWidth={2} style={{ marginRight: 6, verticalAlign: -2 }} />
            Настроить брифинг
          </button>
          <button
            type="button"
            className="button"
            onClick={() => setHistoryOpen(true)}
          >
            <History size={14} strokeWidth={2} style={{ marginRight: 6, verticalAlign: -2 }} />
            История брифингов
          </button>
        </div>
      </div>

      <MorningBriefCard />

      {generatedBrief && (
        <div id="brief-preview">
          <BriefPreview brief={generatedBrief} onSendEmail={() => showToast('Брифинг отправлен на email!')} onDownloadPdf={() => showToast('Генерирую PDF…')} />
        </div>
      )}

      <BriefingConfigModal
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        dateStart={dateStart}
        dateEnd={dateEnd}
        onDateStartChange={setDateStart}
        onDateEndChange={setDateEnd}
        onGenerate={handleGenerate}
        isGenerating={isGenerating}
        weeklyEmailEnabled={weeklyEmailEnabled}
        onToggleWeeklyEmail={setWeeklyEmailEnabled}
        schedule={schedule}
        onScheduleChange={setSchedule}
        onSaveSchedule={handleSaveSchedule}
      />

      <BriefingHistoryModal
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        briefs={getAllSeededBriefs()}
        onSelect={(brief) => {
          setGeneratedBrief(brief);
          setTimeout(
            () => document.getElementById('brief-preview')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
            50,
          );
        }}
      />

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
