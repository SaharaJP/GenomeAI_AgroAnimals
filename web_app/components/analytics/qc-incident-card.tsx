'use client';
import { X, AlertTriangle } from 'lucide-react';
import { dismissQcIncident, type QcIncident } from '@/lib/api/qc-client';
import { useState } from 'react';

interface Props {
  incident: QcIncident;
  onClose: () => void;
  onDismissed: (id: string) => void;
}

const SEVERITY_LABEL: Record<string, string> = {
  info: 'Информация',
  warn: 'Предупреждение',
  high: 'Высокая',
};
const SEVERITY_COLOR: Record<string, string> = {
  info: '#3b82f6',
  warn: '#f59e0b',
  high: '#ef4444',
};

export function QcIncidentCard({ incident, onClose, onDismissed }: Props) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDismiss() {
    setWorking(true);
    setError(null);
    try {
      await dismissQcIncident(incident.incident_id);
      onDismissed(incident.incident_id);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setWorking(false);
    }
  }

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 250,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 24, width: '100%', maxWidth: 520,
        position: 'relative',
      }}>
        <button onClick={onClose} aria-label="Закрыть"
          style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <AlertTriangle size={18} color={SEVERITY_COLOR[incident.severity] || '#f59e0b'} />
          <h3 style={{ margin: 0, fontSize: 18 }}>QC-инцидент</h3>
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 4,
            background: (SEVERITY_COLOR[incident.severity] || '#f59e0b') + '20',
            color: SEVERITY_COLOR[incident.severity] || '#f59e0b',
          }}>{SEVERITY_LABEL[incident.severity] || incident.severity}</span>
        </div>

        <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
          <strong>Метрика:</strong> {incident.metric_id} &nbsp;
          <strong>Период:</strong> {incident.period_start.slice(0, 10)} — {incident.period_end?.slice(0, 10) ?? 'активен'}
        </div>

        {incident.root_cause && (
          <div style={{ marginBottom: 12, fontWeight: 600 }}>{incident.root_cause}</div>
        )}
        {incident.ai_description && (
          <p style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--text)' }}>{incident.ai_description}</p>
        )}
        {incident.affected_sensors.length > 0 && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            Затронуто: {incident.affected_sensors.join(', ')}
          </div>
        )}

        {error && <div style={{ color: 'var(--danger, #b00020)', fontSize: 12, marginTop: 12 }}>{error}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button className="btn-outline" onClick={onClose} disabled={working}>Закрыть</button>
          <button className="btn-outline" onClick={handleDismiss} disabled={working}>
            {working ? 'Скрываю…' : 'Отметить как ложное'}
          </button>
        </div>
      </div>
    </div>
  );
}
