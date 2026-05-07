'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { ChevronRight, Settings, Lightbulb, Zap, MoreVertical, Pencil, Trash2 } from 'lucide-react';
import {
  type InsightStatus, type InsightItem,
  SEVERITY_BADGE, SEVERITY_LABEL, formatRuDate,
} from '@/lib/api/insights';
import {
  fetchInsights, deleteInsight, scanNow,
} from '@/lib/api/insights-client';
import { TriageTabs } from '@/components/insights/triage-tabs';
import { InsightSettingsDialog } from '@/components/insights/insight-settings-dialog';
import { useAuth } from '@/components/auth/auth-provider';

const PAGE_SIZE = 10;

function toast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export default function InsightsPage() {
  const { me } = useAuth();
  const farmLabel = me?.scope?.active_farm_id ?? 'INV_FARM_001';

  const [items, setItems] = useState<InsightItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<InsightStatus>('to_check');
  const [page, setPage] = useState(0);
  const [scanning, setScanning] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchInsights();
      setItems(data.items);
    } catch {
      toast('Ошибка загрузки инсайтов');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  // Close row menu on outside click
  useEffect(() => {
    if (!openMenuId) return;
    function onDocClick() { setOpenMenuId(null); }
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, [openMenuId]);

  const counts: Record<InsightStatus, number> = {
    to_check: items.filter((i) => i.status === 'to_check').length,
    to_follow_up: items.filter((i) => i.status === 'to_follow_up').length,
    done: items.filter((i) => i.status === 'done').length,
  };
  const filtered = items.filter((i) => i.status === activeTab);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  async function onScanNow() {
    setScanning(true);
    try {
      const res = await scanNow(farmLabel);
      toast(`Найдено новых инсайтов: ${res.count}`);
      await refetch();
    } catch (e: unknown) {
      const msg = String(e);
      if (msg.includes('scan_in_progress')) toast('Сканирование уже идёт');
      else if (msg.includes('ai_unavailable')) toast('ИИ недоступен, попробуйте через минуту');
      else toast('Ошибка сканирования');
    } finally {
      setScanning(false);
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Удалить инсайт?')) return;
    try {
      await deleteInsight(id);
      setItems((prev) => prev.filter((i) => i.insight_id !== id));
      toast('Инсайт удалён');
    } catch {
      toast('Ошибка удаления');
    } finally {
      setOpenMenuId(null);
    }
  }

  return (
    <div>
      <div className="insights-page-header">
        <div>
          <h1 className="page-title" style={{ marginBottom: 2 }}>Инсайты</h1>
          <p className="page-subtitle">Аналитические выводы и рекомендации по стаду</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-outline" onClick={onScanNow} disabled={scanning}>
            <Zap size={14} />
            {scanning ? 'Сканирую данные…' : 'Сканировать сейчас'}
          </button>
          <button className="btn-outline" onClick={() => setSettingsOpen(true)}>
            <Settings size={14} />
            Настройка инсайтов
          </button>
        </div>
      </div>

      <TriageTabs
        active={activeTab}
        counts={counts}
        onChange={(t) => { setActiveTab(t); setPage(0); }}
      />

      {loading ? (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>
        </div>
      ) : paginated.length === 0 ? (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <Lightbulb size={32} color="var(--text-muted)" />
          <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 14 }}>
            Нет инсайтов в этой категории. AI-сканер запустится в следующий цикл (или нажмите ⚡).
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 40 }}></th>
                <th>Инсайт</th>
                <th>Ферма</th>
                <th>Период</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((insight) => {
                const goDetail = () => { window.location.href = `/insights/${insight.insight_id}`; };
                return (
                  <tr key={insight.insight_id} style={{ cursor: 'pointer' }}>
                    <td style={{ textAlign: 'center', paddingRight: 4 }} onClick={goDetail}>
                      {insight.status === 'to_check' && (
                        <div className="insight-unread-dot" style={{ margin: '0 auto' }} />
                      )}
                    </td>
                    <td onClick={goDetail}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <span className={`badge ${SEVERITY_BADGE[insight.severity as keyof typeof SEVERITY_BADGE]}`}>
                            {SEVERITY_LABEL[insight.severity as keyof typeof SEVERITY_LABEL]}
                          </span>
                          {insight.animal_ids.length > 0 && (
                            <span className="badge badge-info" style={{ fontSize: 10 }}>
                              ID {insight.animal_ids.slice(0, 2).join(', ')}
                              {insight.animal_ids.length > 2 ? ` +${insight.animal_ids.length - 2}` : ''}
                            </span>
                          )}
                          {insight.edited_at && (
                            <span className="badge" style={{ fontSize: 10, background: 'var(--bg-muted)' }}>
                              Отредактировано
                            </span>
                          )}
                        </div>
                        <span className="insight-row-title">{insight.title}</span>
                        <span className="insight-row-subtitle">
                          {(insight.body || '').slice(0, 80)}…
                        </span>
                      </div>
                    </td>
                    <td onClick={goDetail}>
                      <span className="badge badge-teal">{farmLabel}</span>
                    </td>
                    <td onClick={goDetail} style={{ whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-muted)' }}>
                      {formatRuDate(insight.date)}
                    </td>
                    <td>
                      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <button
                          aria-label="Действия"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenMenuId(openMenuId === insight.insight_id ? null : insight.insight_id);
                          }}
                          style={{
                            background: 'none', border: 'none',
                            cursor: 'pointer', padding: 4,
                            color: 'var(--text-muted)',
                          }}
                        >
                          <MoreVertical size={16} />
                        </button>
                        {openMenuId === insight.insight_id && (
                          <div
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              position: 'absolute', top: 28, right: 0, zIndex: 10,
                              background: 'var(--panel)', border: '1px solid var(--border)',
                              borderRadius: 6, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                              minWidth: 140,
                            }}
                          >
                            <Link
                              href={`/insights/${insight.insight_id}?edit=1`}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '8px 12px', fontSize: 13,
                                textDecoration: 'none', color: 'var(--text)',
                              }}
                            >
                              <Pencil size={14} /> Изменить
                            </Link>
                            <button
                              onClick={() => onDelete(insight.insight_id)}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '8px 12px', fontSize: 13,
                                color: 'var(--danger, #b00020)',
                                background: 'none', border: 'none',
                                cursor: 'pointer', width: '100%', textAlign: 'left',
                              }}
                            >
                              <Trash2 size={14} /> Удалить
                            </button>
                          </div>
                        )}
                        <Link
                          href={`/insights/${insight.insight_id}`}
                          onClick={(e: React.MouseEvent) => e.stopPropagation()}
                          style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}
                        >
                          <ChevronRight size={16} />
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
          <button className="btn-outline" style={{ padding: '4px 10px', fontSize: 12 }} disabled={page === 0} onClick={() => setPage(Math.max(0, page - 1))}>← Назад</button>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{page + 1} / {totalPages}</span>
          <button className="btn-outline" style={{ padding: '4px 10px', fontSize: 12 }} disabled={page >= totalPages - 1} onClick={() => setPage(Math.min(totalPages - 1, page + 1))}>Вперёд →</button>
        </div>
      )}

      <InsightSettingsDialog
        farmId={farmLabel}
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => { toast('Настройки сохранены'); refetch(); }}
      />
    </div>
  );
}
