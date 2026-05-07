'use client';

import { use, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import { type InsightItem, InsightStatus, formatRuDate } from '@/lib/api/insights';
import { fetchInsight, deleteInsight } from '@/lib/api/insights-client';
import { InsightDetail } from '@/components/insights/insight-detail';
import { InsightEditDialog } from '@/components/insights/insight-edit-dialog';

function toast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export default function InsightDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const sp = useSearchParams();
  const [insight, setInsight] = useState<InsightItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [status, setStatus] = useState<InsightStatus>('to_check');
  const [editOpen, setEditOpen] = useState(sp.get('edit') === '1');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await fetchInsight(id);
        if (cancelled) return;
        setInsight(data);
        setStatus((data.status as InsightStatus) ?? 'to_check');
        setNotFound(false);
      } catch {
        if (!cancelled) setNotFound(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  async function onDelete() {
    if (!insight) return;
    if (!confirm('Удалить инсайт?')) return;
    try {
      await deleteInsight(insight.insight_id);
      toast('Инсайт удалён');
      router.push('/insights');
    } catch {
      toast('Ошибка удаления');
    }
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>;
  }

  if (notFound || !insight) {
    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Link
            href="/insights"
            style={{
              fontSize: 13, color: 'var(--accent-text)',
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}
          >
            <ArrowLeft size={13} /> Инсайты
          </Link>
        </div>
        <h1 className="page-title">Инсайт не найден</h1>
        <p className="page-subtitle">Инсайт {id} не существует или был удалён.</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 12, gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
          {insight.edited_at && (
            <span className="badge" style={{ fontSize: 11, background: 'var(--bg-muted)' }}>
              Отредактировано {formatRuDate((insight.edited_at as string).split('T')[0])}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-outline" onClick={() => setEditOpen(true)}>
            <Pencil size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            Изменить
          </button>
          <button
            className="btn-outline"
            style={{ color: 'var(--danger, #b00020)' }}
            onClick={onDelete}
          >
            <Trash2 size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            Удалить
          </button>
        </div>
      </div>

      <InsightDetail insight={insight} status={status} onStatusChange={setStatus} />

      {editOpen && (
        <InsightEditDialog
          insight={insight}
          onClose={() => setEditOpen(false)}
          onSaved={(updated) => { setInsight(updated); toast('Изменения сохранены'); }}
        />
      )}
    </div>
  );
}
