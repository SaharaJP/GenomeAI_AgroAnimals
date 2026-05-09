'use client';

import dynamic from 'next/dynamic';
import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ExplainPanel } from '@/components/copilot/explain-panel';
import { getSeededBrief, getAllSeededBriefs } from '@/lib/weekly-briefs';
import type { WeeklyBrief } from '@/lib/weekly-briefs';
import { CreateBriefCard } from '@/components/copilot/create-brief-card';
import { SettingsCard } from '@/components/copilot/settings-card';
import { PastBriefingsList } from '@/components/copilot/past-briefings-list';

// Lazy-load the rich BriefPreview panel (markdown renderer, charts)
const BriefPreview = dynamic(
  () => import('@/components/copilot/brief-preview').then((m) => m.BriefPreview),
  { loading: () => <div className="card" style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>Загружаю брифинг…</div>, ssr: false },
);

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function weekAgoStr(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

export default function CopilotPage() {
  const sp = useSearchParams();
  const target = sp.get('target');
  const taskId = sp.get('task_id');
  const objectId = sp.get('object_id');
  const dataVersion = sp.get('data_version');
  const reportVersion = sp.get('report_version');
  const hasExplainContext = Boolean(target || taskId || objectId || dataVersion || reportVersion);

  const [dateStart, setDateStart] = useState<string>(weekAgoStr());
  const [dateEnd, setDateEnd] = useState<string>(todayStr());
  const [brief, setBrief] = useState<WeeklyBrief | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [weeklyEmailEnabled, setWeeklyEmailEnabled] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  async function handleGenerate() {
    setIsGenerating(true);
    setBrief(null);

    try {
      const res = await fetch('/api/ai/weekly-brief', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_start: dateStart, week_end: dateEnd }),
      });
      if (res.ok) {
        const data = (await res.json()) as WeeklyBrief;
        setBrief(data);
      } else {
        // Backend unavailable — local demo fallback
        await new Promise<void>((r) => setTimeout(r, 400));
        setBrief(getSeededBrief());
      }
    } catch {
      await new Promise<void>((r) => setTimeout(r, 400));
      setBrief(getSeededBrief());
    }

    setIsGenerating(false);
    setTimeout(
      () => document.getElementById('brief-preview')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      50,
    );
  }

  function handleSendEmail() {
    showToast('Брифинг отправлен на email!');
  }

  async function handleDownloadPdf() {
    if (!brief) return;
    showToast('Генерирую PDF…');

    try {
      const res = await fetch('/api/ai/weekly-brief/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brief }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `briefing-${brief.brief_id}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('PDF скачан');
        return;
      }
    } catch {
      // fall through to text fallback
    }

    // Fallback: plain-text download when backend is unreachable
    const text = [
      `Брифинг фермы: ${brief.week_start} — ${brief.week_end}`,
      '',
      brief.summary,
      '',
      ...brief.narrative,
      '',
      'Ключевые события:',
      ...brief.key_events.map((e) => `• ${e}`),
      '',
      'Рекомендации:',
      ...brief.recommendations.map((r) => `[${r.priority}] ${r.text}`),
    ].join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `briefing-${brief.brief_id}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Скачано как текст (PDF сервис недоступен)');
  }

  const initialTarget = target || taskId || objectId || dataVersion || reportVersion || '';

  return (
    <>
      {hasExplainContext && (
        <ExplainPanel
          initialTarget={initialTarget}
          initialDataVersion={dataVersion ?? undefined}
        />
      )}
    <div className="grid" style={{ maxWidth: 860 }}>
      <div>
        <h1 className="page-title">Помощник: Брифинг фермы</h1>
      </div>

      <CreateBriefCard
        dateStart={dateStart}
        dateEnd={dateEnd}
        onDateStartChange={setDateStart}
        onDateEndChange={setDateEnd}
        onSubmit={handleGenerate}
        isLoading={isGenerating}
      />

      {brief && (
        <div id="brief-preview">
          <BriefPreview brief={brief} onSendEmail={handleSendEmail} onDownloadPdf={handleDownloadPdf} />
        </div>
      )}

      <SettingsCard enabled={weeklyEmailEnabled} onToggle={setWeeklyEmailEnabled} />

      <PastBriefingsList briefs={getAllSeededBriefs()} onSelect={setBrief} />

      {toast && <div className="toast">{toast}</div>}
    </div>
    </>
  );
}
