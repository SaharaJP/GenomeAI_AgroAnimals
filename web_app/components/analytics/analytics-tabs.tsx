'use client';
import { useState, useCallback, useEffect, useRef } from 'react';
import { X, Plus, GitCompare, PenLine, Copy, BarChart2, AlertTriangle, Info, Pencil } from 'lucide-react';
import { ProductionTab } from './production-tab';
import { ReproductionTab } from './reproduction-tab';
import { HealthTab } from './health-tab';
import { FeedTab } from './feed-tab';
import { BehaviorTab } from './behavior-tab';
import { HerdTab } from './herd-tab';
import { WeatherTab } from './weather-tab';
import { FinanceTab } from './finance-tab';
import { AddChartDialog } from './add-chart-dialog';
import { AnalyticsOverlaysProvider, useOverlays } from './analytics-overlays-context';
import { useAuth } from '@/components/auth/auth-provider';

interface Tab {
  id: string;
  label: string;
  soon?: boolean;
}

const INITIAL_TABS: Tab[] = [
  { id: 'production',   label: 'Продуктивность' },
  { id: 'feed',         label: 'Корм' },
  { id: 'reproduction', label: 'Воспроизводство' },
  { id: 'health',       label: 'Здоровье' },
  { id: 'behavior',     label: 'Поведение' },
  { id: 'herd',         label: 'Состав стада' },
  { id: 'weather',      label: 'Погода' },
  { id: 'finance',      label: 'Финансы' },
];

type ModalType =
  | { type: 'rename-panel'; currentLabel: string }
  | { type: 'chart-alert'; chartTitle: string; tabId: string; chartKey: string }
  | { type: 'chart-info'; chartTitle: string }
  | { type: 'chart-rename'; chartTitle: string; tabId: string; chartKey: string }
  | { type: 'compare' }
  | null;

function SoonState() {
  return (
    <div className="an-soon">
      <BarChart2 size={36} color="var(--border-strong)" />
      <p style={{ margin: '12px 0 4px', fontWeight: 600, color: 'var(--text-secondary)' }}>Скоро</p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
        Этот таб появится в следующих версиях
      </p>
    </div>
  );
}

function CompareModal({
  initial,
  onClose,
  onCommit,
}: {
  initial?: { a: string; b: string };
  onClose: () => void;
  onCommit: (a: string, b: string) => void;
}) {
  const todayIso = new Date().toISOString().split('T')[0];
  const monthAgoIso = new Date(Date.now() - 30 * 86400000).toISOString().split('T')[0];
  const [a, setA] = useState(initial?.a ?? monthAgoIso);
  const [b, setB] = useState(initial?.b ?? todayIso);
  return (
    <Modal title="Сравнить периоды" onClose={onClose}>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
        Выберите два периода для сравнения графиков текущей панели.
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>ПЕРИОД А</label>
          <input type="date" className="input" style={{ width: '100%' }} value={a} onChange={(e) => setA(e.target.value)} />
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>ПЕРИОД Б</label>
          <input type="date" className="input" style={{ width: '100%' }} value={b} onChange={(e) => setB(e.target.value)} />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button className="btn-outline" onClick={onClose}>Отмена</button>
        <button
          className="btn-primary-teal"
          onClick={() => {
            if (!a || !b) return;
            onCommit(a, b);
          }}
        >
          Сравнить
        </button>
      </div>
    </Modal>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div style={{ background: 'var(--surface, #fff)', borderRadius: 12, padding: '24px', minWidth: 360, maxWidth: 480, boxShadow: '0 8px 32px rgba(0,0,0,0.18)', position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function HeaderToggles() {
  const { showQc, showEvents, setShowQc, setShowEvents } = useOverlays();
  const btn = (active: boolean): React.CSSProperties => ({
    padding: '4px 10px',
    fontSize: 12,
    border: '1px solid var(--border)',
    borderRadius: 6,
    background: active ? 'var(--accent-soft, #e0f2fe)' : 'transparent',
    color: active ? 'var(--accent-text, #0369a1)' : 'var(--text-secondary)',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
  });
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <button style={btn(showQc)} onClick={() => setShowQc(!showQc)} aria-pressed={showQc}>
        ⚙ QC: {showQc ? 'вкл' : 'выкл'}
      </button>
      <button style={btn(showEvents)} onClick={() => setShowEvents(!showEvents)} aria-pressed={showEvents}>
        📍 События: {showEvents ? 'вкл' : 'выкл'}
      </button>
    </div>
  );
}

export function AnalyticsTabs() {
  const { me } = useAuth();
  const farmId = me?.scope?.active_farm_id ?? 'INV_FARM_001';
  const [tabs, setTabs] = useState<Tab[]>(INITIAL_TABS);
  const [activeId, setActiveId] = useState('production');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [addedCharts, setAddedCharts] = useState<Record<string, string[]>>({});
  const [removedBuiltins, setRemovedBuiltins] = useState<Record<string, string[]>>({});
  const [chartTitles, setChartTitles] = useState<Record<string, Record<string, string>>>({});
  const [chartAlerts, setChartAlerts] = useState<Record<string, Record<string, string>>>({});
  const [comparePeriods, setComparePeriods] = useState<Record<string, { a: string; b: string }>>({});
  const [modal, setModal] = useState<ModalType>(null);
  const [renamePanelValue, setRenamePanelValue] = useState('');
  const [alertThreshold, setAlertThreshold] = useState('');
  const [chartRenameValue, setChartRenameValue] = useState('');
  const renamePanelRef = useRef<HTMLInputElement>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2800);
  }, []);

  const closeTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTabs(prev => {
      const next = prev.filter(t => t.id !== id);
      if (activeId === id && next.length > 0) setActiveId(next[0].id);
      return next;
    });
  };

  const handleAddChart = useCallback(() => setDialogOpen(true), []);

  const handleMetricAdd = useCallback((metricId: string) => {
    setDialogOpen(false);
    setAddedCharts(prev => ({ ...prev, [activeId]: [...(prev[activeId] ?? []), metricId] }));
    showToast('График добавлен на панель');
  }, [showToast, activeId]);

  const handleRemoveChart = useCallback((tabId: string, metricId: string) => {
    setAddedCharts(prev => ({ ...prev, [tabId]: (prev[tabId] ?? []).filter(id => id !== metricId) }));
  }, []);

  const handleRemoveBuiltin = useCallback((tabId: string, key: string) => {
    setRemovedBuiltins(prev => ({
      ...prev,
      [tabId]: prev[tabId]?.includes(key) ? prev[tabId] : [...(prev[tabId] ?? []), key],
    }));
    showToast('График убран с панели');
  }, [showToast]);

  const handleRequestRename = useCallback((tabId: string, chartKey: string, currentTitle: string) => {
    setChartRenameValue(currentTitle);
    setModal({ type: 'chart-rename', chartTitle: currentTitle, tabId, chartKey });
  }, []);

  const handleRequestAlert = useCallback((tabId: string, chartKey: string, currentTitle: string) => {
    setAlertThreshold(chartAlerts[tabId]?.[chartKey] ?? '');
    setModal({ type: 'chart-alert', chartTitle: currentTitle, tabId, chartKey });
  }, [chartAlerts]);

  const commitChartRename = useCallback(() => {
    const v = chartRenameValue.trim();
    if (!v || !modal || modal.type !== 'chart-rename') { setModal(null); return; }
    setChartTitles(prev => ({
      ...prev,
      [modal.tabId]: { ...(prev[modal.tabId] ?? {}), [modal.chartKey]: v },
    }));
    setModal(null);
    showToast(`График переименован в «${v}»`);
  }, [chartRenameValue, modal, showToast]);

  const commitChartAlert = useCallback(() => {
    if (!alertThreshold || !modal || modal.type !== 'chart-alert') return;
    setChartAlerts(prev => ({
      ...prev,
      [modal.tabId]: { ...(prev[modal.tabId] ?? {}), [modal.chartKey]: alertThreshold },
    }));
    setModal(null);
    showToast(`Алерт установлен: «${modal.chartTitle}» > ${alertThreshold}`);
  }, [alertThreshold, modal, showToast]);

  // Panel actions
  const handleRenamePanel = () => {
    const active = tabs.find(t => t.id === activeId);
    setRenamePanelValue(active?.label ?? '');
    setModal({ type: 'rename-panel', currentLabel: active?.label ?? '' });
    setTimeout(() => renamePanelRef.current?.focus(), 50);
  };

  const commitRenamePanel = () => {
    const v = renamePanelValue.trim();
    if (!v) return;
    setTabs(prev => prev.map(t => t.id === activeId ? { ...t, label: v } : t));
    setModal(null);
    showToast('Панель переименована');
  };

  const handleCopyPanel = () => {
    const active = tabs.find(t => t.id === activeId);
    if (!active) return;
    const newId = `${active.id}_copy_${Date.now()}`;
    const newTab: Tab = { id: newId, label: `${active.label} (копия)`, soon: active.soon };
    setTabs(prev => [...prev, newTab]);
    setAddedCharts(prev => ({ ...prev, [newId]: [...(prev[activeId] ?? [])] }));
    setActiveId(newId);
    showToast(`Панель «${active.label}» скопирована`);
  };

  const handleCompare = () => setModal({ type: 'compare' });

  // Chart info modal still uses event for compactness (read-only — no save side effect)
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail.startsWith('Информация: ')) {
        setModal({ type: 'chart-info', chartTitle: detail.replace('Информация: ', '') });
      }
    };
    window.addEventListener('chart-action', handler);
    return () => window.removeEventListener('chart-action', handler);
  }, []);

  const activeTab = tabs.find(t => t.id === activeId);

  return (
    <AnalyticsOverlaysProvider farmId={farmId}>
    <div>
      {/* Tab bar + toolbar */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div className="an-tab-bar">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`an-tab-btn${activeId === tab.id ? ' an-tab-btn-active' : ''}`}
              onClick={() => setActiveId(tab.id)}
            >
              {tab.label}
              <span
                className="an-tab-close"
                role="button"
                aria-label={`Закрыть ${tab.label}`}
                onClick={e => closeTab(tab.id, e)}
              >
                <X size={9} />
              </span>
            </button>
          ))}
          <button
            className="an-tab-add"
            onClick={handleCopyPanel}
            aria-label="Добавить таб"
            title="Копировать текущую панель"
          >
            <Plus size={13} />
          </button>
        </div>

        <div className="an-toolbar">
          <button className="btn-outline" style={{ fontSize: 12, padding: '5px 11px', gap: 5 }}
            onClick={handleCompare}>
            <GitCompare size={13} /> Сравнить графики
          </button>
          <button className="btn-outline" style={{ fontSize: 12, padding: '5px 11px', gap: 5 }}
            onClick={handleRenamePanel}>
            <PenLine size={13} /> Переименовать панель
          </button>
          <button className="btn-outline" style={{ fontSize: 12, padding: '5px 11px', gap: 5 }}
            onClick={handleCopyPanel}>
            <Copy size={13} /> Копировать панель
          </button>
          <HeaderToggles />
          <button
            className="button button-primary"
            style={{ fontSize: 12, padding: '5px 13px', gap: 5 }}
            onClick={handleAddChart}
          >
            <Plus size={13} /> Добавить график
          </button>
        </div>
      </div>

      {comparePeriods[activeId] && (
        <div
          style={{
            marginTop: 12, padding: '6px 10px',
            background: 'var(--accent-subtle, #e6f7f5)', color: 'var(--accent-text, #0a6b6b)',
            borderRadius: 8, fontSize: 12, display: 'flex', alignItems: 'center', gap: 8,
          }}
        >
          <GitCompare size={12} />
          Сравнение периодов: <strong>{comparePeriods[activeId].a}</strong>
          <span>↔</span>
          <strong>{comparePeriods[activeId].b}</strong>
          <button
            type="button"
            onClick={() => setComparePeriods((prev) => {
              const copy = { ...prev };
              delete copy[activeId];
              return copy;
            })}
            style={{
              marginLeft: 'auto', background: 'none', border: 'none',
              cursor: 'pointer', color: 'inherit', padding: 2, display: 'inline-flex',
            }}
            aria-label="Снять сравнение"
            title="Снять сравнение"
          >
            <X size={11} />
          </button>
        </div>
      )}

      {/* Tab content */}
      <div style={{ marginTop: 20 }}>
        {!activeTab ? (
          <SoonState />
        ) : activeTab.soon ? (
          <SoonState />
        ) : activeTab.id === 'production' ? (
          <ProductionTab onAddChart={handleAddChart} addedMetricIds={addedCharts['production'] ?? []} onRemoveChart={(id) => handleRemoveChart('production', id)} removedBuiltinIds={removedBuiltins['production'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('production', k)} titleOverrides={chartTitles['production'] ?? {}} alertThresholds={chartAlerts['production'] ?? {}} onRequestRename={(k, t) => handleRequestRename('production', k, t)} onRequestAlert={(k, t) => handleRequestAlert('production', k, t)} />
        ) : activeTab.id === 'feed' ? (
          <FeedTab onAddChart={handleAddChart} addedMetricIds={addedCharts['feed'] ?? []} onRemoveChart={(id) => handleRemoveChart('feed', id)} removedBuiltinIds={removedBuiltins['feed'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('feed', k)} titleOverrides={chartTitles['feed'] ?? {}} alertThresholds={chartAlerts['feed'] ?? {}} onRequestRename={(k, t) => handleRequestRename('feed', k, t)} onRequestAlert={(k, t) => handleRequestAlert('feed', k, t)} />
        ) : activeTab.id === 'reproduction' ? (
          <ReproductionTab onAddChart={handleAddChart} addedMetricIds={addedCharts['reproduction'] ?? []} onRemoveChart={(id) => handleRemoveChart('reproduction', id)} removedBuiltinIds={removedBuiltins['reproduction'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('reproduction', k)} titleOverrides={chartTitles['reproduction'] ?? {}} alertThresholds={chartAlerts['reproduction'] ?? {}} onRequestRename={(k, t) => handleRequestRename('reproduction', k, t)} onRequestAlert={(k, t) => handleRequestAlert('reproduction', k, t)} />
        ) : activeTab.id === 'health' ? (
          <HealthTab onAddChart={handleAddChart} addedMetricIds={addedCharts['health'] ?? []} onRemoveChart={(id) => handleRemoveChart('health', id)} removedBuiltinIds={removedBuiltins['health'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('health', k)} titleOverrides={chartTitles['health'] ?? {}} alertThresholds={chartAlerts['health'] ?? {}} onRequestRename={(k, t) => handleRequestRename('health', k, t)} onRequestAlert={(k, t) => handleRequestAlert('health', k, t)} />
        ) : activeTab.id === 'behavior' ? (
          <BehaviorTab onAddChart={handleAddChart} addedMetricIds={addedCharts['behavior'] ?? []} onRemoveChart={(id) => handleRemoveChart('behavior', id)} removedBuiltinIds={removedBuiltins['behavior'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('behavior', k)} titleOverrides={chartTitles['behavior'] ?? {}} alertThresholds={chartAlerts['behavior'] ?? {}} onRequestRename={(k, t) => handleRequestRename('behavior', k, t)} onRequestAlert={(k, t) => handleRequestAlert('behavior', k, t)} />
        ) : activeTab.id === 'herd' ? (
          <HerdTab onAddChart={handleAddChart} addedMetricIds={addedCharts[activeTab.id] ?? []} onRemoveChart={(id) => handleRemoveChart(activeTab.id, id)} removedBuiltinIds={removedBuiltins[activeTab.id] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin(activeTab.id, k)} titleOverrides={chartTitles[activeTab.id] ?? {}} alertThresholds={chartAlerts[activeTab.id] ?? {}} onRequestRename={(k, t) => handleRequestRename(activeTab.id, k, t)} onRequestAlert={(k, t) => handleRequestAlert(activeTab.id, k, t)} />
        ) : activeTab.id === 'weather' ? (
          <WeatherTab onAddChart={handleAddChart} addedMetricIds={addedCharts['weather'] ?? []} onRemoveChart={(id) => handleRemoveChart('weather', id)} removedBuiltinIds={removedBuiltins['weather'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('weather', k)} titleOverrides={chartTitles['weather'] ?? {}} alertThresholds={chartAlerts['weather'] ?? {}} onRequestRename={(k, t) => handleRequestRename('weather', k, t)} onRequestAlert={(k, t) => handleRequestAlert('weather', k, t)} />
        ) : activeTab.id === 'finance' ? (
          <FinanceTab onAddChart={handleAddChart} addedMetricIds={addedCharts['finance'] ?? []} onRemoveChart={(id) => handleRemoveChart('finance', id)} removedBuiltinIds={removedBuiltins['finance'] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin('finance', k)} titleOverrides={chartTitles['finance'] ?? {}} alertThresholds={chartAlerts['finance'] ?? {}} onRequestRename={(k, t) => handleRequestRename('finance', k, t)} onRequestAlert={(k, t) => handleRequestAlert('finance', k, t)} />
        ) : activeTab.id.endsWith('_copy') || activeTab.id.includes('_copy_') ? (
          <ProductionTab onAddChart={handleAddChart} addedMetricIds={addedCharts[activeTab.id] ?? []} onRemoveChart={(id) => handleRemoveChart(activeTab.id, id)} removedBuiltinIds={removedBuiltins[activeTab.id] ?? []} onRemoveBuiltin={(k) => handleRemoveBuiltin(activeTab.id, k)} titleOverrides={chartTitles[activeTab.id] ?? {}} alertThresholds={chartAlerts[activeTab.id] ?? {}} onRequestRename={(k, t) => handleRequestRename(activeTab.id, k, t)} onRequestAlert={(k, t) => handleRequestAlert(activeTab.id, k, t)} />
        ) : (
          <SoonState />
        )}
      </div>

      {/* Add chart dialog */}
      <AddChartDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onAdd={handleMetricAdd} />

      {/* Modals */}
      {modal?.type === 'rename-panel' && (
        <Modal title="Переименовать панель" onClose={() => setModal(null)}>
          <input
            ref={renamePanelRef}
            className="input"
            value={renamePanelValue}
            onChange={(e) => setRenamePanelValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && commitRenamePanel()}
            maxLength={60}
            style={{ width: '100%', marginBottom: 16 }}
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-outline" onClick={() => setModal(null)}>Отмена</button>
            <button className="btn-primary-teal" onClick={commitRenamePanel}>Сохранить</button>
          </div>
        </Modal>
      )}

      {modal?.type === 'compare' && (
        <CompareModal
          onClose={() => setModal(null)}
          initial={comparePeriods[activeId]}
          onCommit={(a, b) => {
            setComparePeriods(prev => ({ ...prev, [activeId]: { a, b } }));
            setModal(null);
            showToast(`Сравнение применено: ${a} ↔ ${b}`);
          }}
        />
      )}

      {modal?.type === 'chart-alert' && (
        <Modal title={`Алерт: ${modal.chartTitle}`} onClose={() => setModal(null)}>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 12px' }}>
            Установите пороговое значение для уведомлений по этому графику.
          </p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Порог &gt;</span>
            <input
              className="input"
              type="number"
              placeholder="например, 200"
              value={alertThreshold}
              onChange={(e) => setAlertThreshold(e.target.value)}
              style={{ width: 120 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-outline" onClick={() => setModal(null)}>Отмена</button>
            <button className="btn-primary-teal" onClick={commitChartAlert}>
              <AlertTriangle size={12} /> Установить алерт
            </button>
          </div>
        </Modal>
      )}

      {modal?.type === 'chart-info' && (
        <Modal title={`Информация: ${modal.chartTitle}`} onClose={() => setModal(null)}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ margin: '0 0 8px' }}><strong>График:</strong> {modal.chartTitle}</p>
            <p style={{ margin: '0 0 8px' }}><strong>Источник:</strong> Реальные данные фермы из БД</p>
            <p style={{ margin: '0 0 8px' }}><strong>Обновление:</strong> Еженедельно</p>
            <p style={{ margin: '0 0 8px' }}><strong>Метод:</strong> Агрегация по ферме / группе животных</p>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 12 }}>
              Данные рассчитываются на основе тест-дней и ежедневных замеров с сенсоров.
            </p>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <button className="btn-outline" onClick={() => setModal(null)}>Закрыть</button>
          </div>
        </Modal>
      )}

      {modal?.type === 'chart-rename' && (
        <Modal title="Переименовать график" onClose={() => setModal(null)}>
          <input
            className="input"
            value={chartRenameValue}
            onChange={(e) => setChartRenameValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') commitChartRename(); }}
            maxLength={80}
            style={{ width: '100%', marginBottom: 16 }}
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-outline" onClick={() => setModal(null)}>Отмена</button>
            <button className="btn-primary-teal" onClick={commitChartRename}>Сохранить</button>
          </div>
        </Modal>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
    </AnalyticsOverlaysProvider>
  );
}
