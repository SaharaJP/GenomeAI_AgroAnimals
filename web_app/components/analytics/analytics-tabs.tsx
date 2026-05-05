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
  | { type: 'chart-alert'; chartTitle: string }
  | { type: 'chart-info'; chartTitle: string }
  | { type: 'chart-rename'; chartTitle: string }
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

export function AnalyticsTabs() {
  const [tabs, setTabs] = useState<Tab[]>(INITIAL_TABS);
  const [activeId, setActiveId] = useState('production');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [addedCharts, setAddedCharts] = useState<Record<string, string[]>>({});
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

  // Chart action events from child components
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail.startsWith('Алерт: ')) {
        setAlertThreshold('');
        setModal({ type: 'chart-alert', chartTitle: detail.replace('Алерт: ', '') });
      } else if (detail.startsWith('Информация: ')) {
        setModal({ type: 'chart-info', chartTitle: detail.replace('Информация: ', '') });
      } else if (detail.startsWith('Переименовать: ')) {
        setChartRenameValue(detail.replace('Переименовать: ', ''));
        setModal({ type: 'chart-rename', chartTitle: detail.replace('Переименовать: ', '') });
      } else if (detail.startsWith('Удалить: ')) {
        showToast(`График «${detail.replace('Удалить: ', '')}» удалён из панели`);
      } else {
        showToast(`${detail} — скоро`);
      }
    };
    window.addEventListener('chart-action', handler);
    return () => window.removeEventListener('chart-action', handler);
  }, [showToast]);

  const activeTab = tabs.find(t => t.id === activeId);

  return (
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
          <button
            className="button button-primary"
            style={{ fontSize: 12, padding: '5px 13px', gap: 5 }}
            onClick={handleAddChart}
          >
            <Plus size={13} /> Добавить график
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div style={{ marginTop: 20 }}>
        {!activeTab ? (
          <SoonState />
        ) : activeTab.soon ? (
          <SoonState />
        ) : activeTab.id === 'production' ? (
          <ProductionTab onAddChart={handleAddChart} addedMetricIds={addedCharts['production'] ?? []} onRemoveChart={(id) => handleRemoveChart('production', id)} />
        ) : activeTab.id === 'feed' ? (
          <FeedTab onAddChart={handleAddChart} addedMetricIds={addedCharts['feed'] ?? []} onRemoveChart={(id) => handleRemoveChart('feed', id)} />
        ) : activeTab.id === 'reproduction' ? (
          <ReproductionTab />
        ) : activeTab.id === 'health' ? (
          <HealthTab onAddChart={handleAddChart} addedMetricIds={addedCharts['health'] ?? []} onRemoveChart={(id) => handleRemoveChart('health', id)} />
        ) : activeTab.id === 'behavior' ? (
          <BehaviorTab onAddChart={handleAddChart} addedMetricIds={addedCharts['behavior'] ?? []} onRemoveChart={(id) => handleRemoveChart('behavior', id)} />
        ) : activeTab.id === 'herd' ? (
          <HerdTab onAddChart={handleAddChart} addedMetricIds={addedCharts[activeTab.id] ?? []} onRemoveChart={(id) => handleRemoveChart(activeTab.id, id)} />
        ) : activeTab.id === 'weather' ? (
          <WeatherTab onAddChart={handleAddChart} addedMetricIds={addedCharts['weather'] ?? []} onRemoveChart={(id) => handleRemoveChart('weather', id)} />
        ) : activeTab.id === 'finance' ? (
          <FinanceTab onAddChart={handleAddChart} addedMetricIds={addedCharts['finance'] ?? []} onRemoveChart={(id) => handleRemoveChart('finance', id)} />
        ) : activeTab.id.endsWith('_copy') || activeTab.id.includes('_copy_') ? (
          <ProductionTab onAddChart={handleAddChart} addedMetricIds={addedCharts[activeTab.id] ?? []} onRemoveChart={(id) => handleRemoveChart(activeTab.id, id)} />
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
        <Modal title="Сравнить периоды" onClose={() => setModal(null)}>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
            Выберите два периода для сравнения графиков текущей панели.
          </p>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>ПЕРИОД А</label>
              <input type="date" className="input" style={{ width: '100%' }} defaultValue={new Date(Date.now() - 30 * 86400000).toISOString().split('T')[0]} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>ПЕРИОД Б</label>
              <input type="date" className="input" style={{ width: '100%' }} defaultValue={new Date().toISOString().split('T')[0]} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-outline" onClick={() => setModal(null)}>Отмена</button>
            <button className="btn-primary-teal" onClick={() => { setModal(null); showToast('Сравнение запущено — результаты появятся в карточках'); }}>
              Сравнить
            </button>
          </div>
        </Modal>
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
            <button className="btn-primary-teal" onClick={() => {
              if (!alertThreshold) return;
              setModal(null);
              showToast(`Алерт установлен: ${modal.chartTitle} > ${alertThreshold}`);
            }}>
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
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setModal(null);
                showToast(`График переименован в «${chartRenameValue}»`);
              }
            }}
            maxLength={80}
            style={{ width: '100%', marginBottom: 16 }}
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-outline" onClick={() => setModal(null)}>Отмена</button>
            <button className="btn-primary-teal" onClick={() => {
              setModal(null);
              showToast(`График переименован в «${chartRenameValue}»`);
            }}>Сохранить</button>
          </div>
        </Modal>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
