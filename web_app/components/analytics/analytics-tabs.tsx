'use client';
import { useState, useCallback, useEffect } from 'react';
import { X, Plus, GitCompare, PenLine, Copy, BarChart2 } from 'lucide-react';
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

export function AnalyticsTabs() {
  const [tabs, setTabs] = useState<Tab[]>(INITIAL_TABS);
  const [activeId, setActiveId] = useState('production');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [addedCharts, setAddedCharts] = useState<Record<string, string[]>>({});

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2800);
  }, []);

  const closeTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTabs(prev => {
      const next = prev.filter(t => t.id !== id);
      if (activeId === id && next.length > 0) {
        setActiveId(next[0].id);
      }
      return next;
    });
  };

  const handleAddChart = useCallback(() => setDialogOpen(true), []);

  const handleMetricAdd = useCallback((metricId: string) => {
    setDialogOpen(false);
    setAddedCharts(prev => ({
      ...prev,
      [activeId]: [...(prev[activeId] ?? []), metricId],
    }));
    showToast('График добавлен на панель');
  }, [showToast, activeId]);

  const handleRemoveChart = useCallback((tabId: string, metricId: string) => {
    setAddedCharts(prev => ({
      ...prev,
      [tabId]: (prev[tabId] ?? []).filter(id => id !== metricId),
    }));
  }, []);

  const stubAction = (label: string) => showToast(`${label} — скоро`);

  useEffect(() => {
    const handler = (e: Event) => showToast((e as CustomEvent<string>).detail + ' — скоро');
    window.addEventListener('chart-action', handler);
    return () => window.removeEventListener('chart-action', handler);
  }, [showToast]);

  const activeTab = tabs.find(t => t.id === activeId);

  return (
    <div>
      {/* Tab bar + toolbar row */}
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
            onClick={() => stubAction('Новый таб')}
            aria-label="Добавить таб"
          >
            <Plus size={13} />
          </button>
        </div>

        <div className="an-toolbar">
          <button className="btn-outline" style={{ fontSize: 12, padding: '5px 11px', gap: 5 }}
            onClick={() => stubAction('Сравнить графики')}
          >
            <GitCompare size={13} /> Сравнить графики
          </button>
          <button className="btn-outline" style={{ fontSize: 12, padding: '5px 11px', gap: 5 }}
            onClick={() => stubAction('Переименовать панель')}
          >
            <PenLine size={13} /> Переименовать панель
          </button>
          <button className="btn-outline" style={{ fontSize: 12, padding: '5px 11px', gap: 5 }}
            onClick={() => stubAction('Копировать панель')}
          >
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
          <ProductionTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['production'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('production', id)}
          />
        ) : activeTab.id === 'feed' ? (
          <FeedTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['feed'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('feed', id)}
          />
        ) : activeTab.id === 'reproduction' ? (
          <ReproductionTab />
        ) : activeTab.id === 'health' ? (
          <HealthTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['health'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('health', id)}
          />
        ) : activeTab.id === 'behavior' ? (
          <BehaviorTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['behavior'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('behavior', id)}
          />
        ) : activeTab.id === 'herd' ? (
          <HerdTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['herd'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('herd', id)}
          />
        ) : activeTab.id === 'weather' ? (
          <WeatherTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['weather'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('weather', id)}
          />
        ) : activeTab.id === 'finance' ? (
          <FinanceTab
            onAddChart={handleAddChart}
            addedMetricIds={addedCharts['finance'] ?? []}
            onRemoveChart={(id) => handleRemoveChart('finance', id)}
          />
        ) : (
          <SoonState />
        )}
      </div>

      {/* Add chart dialog */}
      <AddChartDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onAdd={handleMetricAdd}
      />

      {/* Toast */}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
