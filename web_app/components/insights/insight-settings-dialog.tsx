'use client';
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { fetchSettings, putSettings, type InsightSettings } from '@/lib/api/insights-client';

const SEVERITIES: Array<{ value: InsightSettings['min_severity']; label: string }> = [
  { value: 'info',   label: 'Все (включая информационные)' },
  { value: 'warn',   label: 'Предупреждения и выше' },
  { value: 'high',   label: 'Высокие и выше' },
  { value: 'urgent', label: 'Только срочные' },
];

const CATEGORIES: Array<{ value: string; label: string }> = [
  { value: 'production',   label: 'Производство' },
  { value: 'reproduction', label: 'Воспроизводство' },
  { value: 'health',       label: 'Здоровье' },
  { value: 'feeding',      label: 'Кормление' },
  { value: 'welfare',      label: 'Благополучие' },
  { value: 'economics',    label: 'Экономика' },
];

interface Props {
  farmId: string;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function InsightSettingsDialog({ farmId, open, onClose, onSaved }: Props) {
  const [settings, setSettings] = useState<InsightSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSettings(null);
    fetchSettings(farmId)
      .then(setSettings)
      .catch((e) => setError(String(e)));
  }, [open, farmId]);

  if (!open) return null;

  function toggleCat(value: string) {
    if (!settings) return;
    const has = settings.enabled_categories.includes(value);
    setSettings({
      ...settings,
      enabled_categories: has
        ? settings.enabled_categories.filter((c) => c !== value)
        : [...settings.enabled_categories, value],
    });
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      await putSettings(farmId, settings);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: 24,
        width: '100%',
        maxWidth: 480,
        position: 'relative',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
      }}>
        <button
          onClick={onClose}
          aria-label="Закрыть"
          style={{
            position: 'absolute', top: 12, right: 12,
            background: 'none', border: 'none',
            cursor: 'pointer', color: 'var(--text-secondary)',
          }}
        ><X size={18} /></button>
        <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>Настройка инсайтов</h3>

        {!settings && !error && (
          <div style={{ color: 'var(--text-muted)' }}>Загрузка…</div>
        )}
        {error && !settings && (
          <div style={{ color: 'var(--danger, #b00020)', fontSize: 13 }}>
            Не удалось загрузить настройки: {error}
          </div>
        )}
        {settings && (
          <>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Порог важности</div>
              {SEVERITIES.map((s) => (
                <label
                  key={s.value}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', cursor: 'pointer' }}
                >
                  <input
                    type="radio"
                    name="insight-severity"
                    checked={settings.min_severity === s.value}
                    onChange={() => setSettings({ ...settings, min_severity: s.value })}
                  />
                  {s.label}
                </label>
              ))}
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Категории</div>
              {CATEGORIES.map((c) => (
                <label
                  key={c.value}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', cursor: 'pointer' }}
                >
                  <input
                    type="checkbox"
                    checked={settings.enabled_categories.includes(c.value)}
                    onChange={() => toggleCat(c.value)}
                  />
                  {c.label}
                </label>
              ))}
            </div>
            {error && (
              <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginBottom: 12 }}>
                {error}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn-outline" onClick={onClose} disabled={saving}>
                Отмена
              </button>
              <button className="btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Сохраняю…' : 'Сохранить'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
