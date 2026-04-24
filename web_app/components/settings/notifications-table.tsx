import { Info } from 'lucide-react';
import { Toggle } from '@/components/ui/toggle';

interface Props {
  kpiInsightsEmail: boolean;
  weeklyBriefing: boolean;
  onKpiChange: (v: boolean) => void;
  onBriefingChange: (v: boolean) => void;
}

export function NotificationsTable({ kpiInsightsEmail, weeklyBriefing, onKpiChange, onBriefingChange }: Props) {
  return (
    <>
      <section className="settings-section">
        <h2 className="settings-section-title">Уведомления</h2>
        <p className="settings-section-subtitle">Выберите, какие уведомления вы хотите получать</p>
        <div className="settings-card">
          <table className="settings-notif-table">
            <thead>
              <tr>
                <th>Feature</th>
                <th>email</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    KPI Инсайты
                    <Info size={13} strokeWidth={1.5} color="var(--text-muted)" />
                  </span>
                </td>
                <td style={{ textAlign: 'right' }}>
                  <Toggle on={kpiInsightsEmail} onChange={onKpiChange} label="KPI Инсайты email" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">Weekly Farm briefings <span className="settings-briefing-badge">Powered by Copilot</span></h2>
        <div className="settings-card settings-briefing-row">
          <div style={{ flex: 1 }}>
            <div className="settings-briefing-title">Еженедельные брифинги фермы от ИИ-помощника</div>
            <div className="settings-briefing-desc">
              Включите, чтобы получать email с брифингом фермы каждый понедельник о Демо-ферме
            </div>
          </div>
          <Toggle on={weeklyBriefing} onChange={onBriefingChange} label="Еженедельный брифинг" />
        </div>
      </section>
    </>
  );
}
