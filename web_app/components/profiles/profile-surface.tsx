'use client';
import { useEffect, useState } from 'react';
import { fetchProfile } from '@/lib/api/profiles-reports-assistant';
import type { AlertItem, AnimalAttributes, DecisionItem, HealthEvent, HealthMetrics, ProfileResponse, WorklistItem } from '@/lib/api/contracts';

type Tab = 'health' | 'productivity' | 'tasks' | 'history';

const TABS: { key: Tab; label: string }[] = [
  { key: 'health',       label: 'Здоровье' },
  { key: 'productivity', label: 'Продуктивность' },
  { key: 'tasks',        label: 'Задачи' },
  { key: 'history',      label: 'История' },
];

function calcAge(birthDate: string | null | undefined): string {
  if (!birthDate) return '—';
  const birth = new Date(birthDate);
  if (isNaN(birth.getTime())) return '—';
  const now = new Date();
  const years = now.getFullYear() - birth.getFullYear() -
    (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate()) ? 1 : 0);
  return `${years} ${years === 1 ? 'год' : years < 5 ? 'года' : 'лет'}`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}

function AnimalHero({ objectId, attrs, metrics, summary }: {
  objectId: string;
  attrs: AnimalAttributes | null | undefined;
  metrics: HealthMetrics | null | undefined;
  summary: ProfileResponse['summary'];
}) {
  const name = attrs?.name ? `${attrs.name} ` : '';
  const title = `${name}№${objectId}`;

  const subParts: string[] = [];
  if (attrs?.breed) subParts.push(attrs.breed);
  if (attrs?.birth_date) subParts.push(calcAge(attrs.birth_date));
  if (attrs?.lactation_number != null && attrs?.days_in_milk != null)
    subParts.push(`Лактация ${attrs.lactation_number}, ${attrs.days_in_milk} ДИМ`);
  if (attrs?.group_label) subParts.push(attrs.group_label);
  if (attrs?.farm_label) subParts.push(attrs.farm_label);

  return (
    <div className="profile-hero">
      <div className="profile-hero-avatar">🐄</div>
      <div>
        <h1 className="profile-hero-name">{title}</h1>
        {subParts.length > 0 && (
          <p className="profile-hero-sub">{subParts.join(' · ')}</p>
        )}
      </div>
      <div className="profile-hero-badges">
        {summary.alerts_open > 0 && (
          <span className="profile-badge profile-badge--danger">⚠ {summary.alerts_open} алерт{summary.alerts_open > 1 ? 'а' : ''}</span>
        )}
        {metrics?.scc != null && metrics.scc > 200 && (
          <span className="profile-badge profile-badge--warning">СКК {metrics.scc}k</span>
        )}
        {metrics?.daily_milk_yield_kg != null && (
          <span className="profile-badge profile-badge--success">Надой {metrics.daily_milk_yield_kg} кг</span>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, sub, valueClass }: {
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="profile-metric-card">
      <p className="profile-metric-label">{label}</p>
      <p className={`profile-metric-value${valueClass ? ` ${valueClass}` : ''}`}>{value ?? '—'}</p>
      {sub && <p className="profile-metric-sub">{sub}</p>}
    </div>
  );
}

function TabHealth({ metrics, alerts, events }: {
  metrics: HealthMetrics | null | undefined;
  alerts: AlertItem[];
  events: HealthEvent[];
}) {
  const actClass = metrics?.activity_score != null
    ? (metrics.activity_score < 40 ? 'profile-metric-value--bad' : metrics.activity_score < 60 ? 'profile-metric-value--warn' : 'profile-metric-value--ok')
    : undefined;
  const sccClass = metrics?.scc != null
    ? (metrics.scc > 400 ? 'profile-metric-value--bad' : metrics.scc > 200 ? 'profile-metric-value--warn' : undefined)
    : undefined;
  const openAlerts = alerts.filter(a => a.status === 'new' || a.status === 'acknowledged');

  return (
    <>
      <div className="profile-metric-row">
        <MetricCard
          label="Активность"
          value={metrics?.activity_score ?? null}
          sub={`норма >${metrics?.activity_norm ?? 60}`}
          valueClass={actClass}
        />
        <MetricCard
          label="СКК (тыс/мл)"
          value={metrics?.scc != null ? `${metrics.scc}k` : null}
          sub={metrics?.scc_trend ?? undefined}
          valueClass={sccClass}
        />
        <MetricCard
          label="БКТ"
          value={metrics?.body_condition_score ?? null}
          sub="норма 2.5–3.5"
        />
      </div>
      <div>
        {openAlerts.length === 0 ? (
          <p className="profile-empty">Активных алертов нет</p>
        ) : openAlerts.map(alert => (
          <div key={alert.alert_id} className="profile-alert-card">
            <p className="profile-alert-title">{alert.title}</p>
            <p className="profile-alert-meta">
              {alert.severity ? `Серьёзность: ${alert.severity}` : ''}
              {alert.deadline ? ` · Срок: ${alert.deadline}` : ''}
              {alert.owner_username ? ` · ${alert.owner_username}` : ''}
            </p>
          </div>
        ))}
      </div>
      <div className="card">
        <p className="profile-kv-title">Последние события здоровья</p>
        {events.length === 0 ? (
          <p className="profile-empty">Событий нет</p>
        ) : events.map((ev, i) => {
          const sevDot = ev.severity === 'high' ? 'profile-task-dot--high'
                        : ev.severity === 'warn' ? 'profile-task-dot--medium'
                        : 'profile-task-dot--low';
          return (
            <div key={ev.event_id ?? `he_${i}`} className="profile-task-row">
              <div className={`profile-task-dot ${sevDot}`} />
              <div>
                <p className="profile-task-title">{ev.event_type ?? '—'}</p>
                <p className="profile-task-meta">
                  {ev.event_date ? formatDate(ev.event_date) : '—'}
                  {ev.treatment ? ` · ${ev.treatment}` : ''}
                  {ev.notes ? ` · ${ev.notes}` : ''}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function TabProductivity({ attrs, metrics }: { attrs: AnimalAttributes | null | undefined; metrics: HealthMetrics | null | undefined }) {
  return (
    <>
      <div className="profile-metric-row">
        <MetricCard
          label="Надой сегодня"
          value={metrics?.daily_milk_yield_kg != null ? `${metrics.daily_milk_yield_kg} кг` : null}
        />
        <MetricCard
          label="Лактация"
          value={attrs?.lactation_number != null ? `№${attrs.lactation_number}` : null}
          sub={attrs?.days_in_milk != null ? `${attrs.days_in_milk} дней в молоке` : undefined}
        />
        <MetricCard
          label="Последний отёл"
          value={formatDate(attrs?.last_calving_date)}
        />
      </div>
      <div className="profile-kv-block">
        <p className="profile-kv-title">Воспроизводство</p>
        <div className="profile-kv-row">
          <span className="profile-kv-key">Статус осеменения</span>
          <span>{attrs?.reproduction_status ?? '—'}</span>
        </div>
        <div className="profile-kv-row">
          <span className="profile-kv-key">Отёлов всего</span>
          <span>{attrs?.total_calvings ?? '—'}</span>
        </div>
        <div className="profile-kv-row">
          <span className="profile-kv-key">Прогноз следующего отёла</span>
          <span>{formatDate(attrs?.next_calving_expected)}</span>
        </div>
      </div>
    </>
  );
}

const PRIORITY_DOT: Record<number, string> = {
  1: 'profile-task-dot--high',
  2: 'profile-task-dot--medium',
  3: 'profile-task-dot--low',
};
const PRIORITY_LABEL: Record<number, string> = {
  1: 'Высокий',
  2: 'Средний',
  3: 'Низкий',
};

function TabTasks({ worklists }: { worklists: WorklistItem[] }) {
  const open = worklists.filter(w => w.status === 'open' || w.status === 'in_progress');
  if (open.length === 0) return <p className="profile-empty">Открытых задач нет</p>;
  return (
    <div className="card">
      <p className="profile-kv-title">Открытые задачи ({open.length})</p>
      {open.map(task => (
        <div key={task.task_id} className="profile-task-row">
          <div className={`profile-task-dot ${PRIORITY_DOT[task.priority] ?? 'profile-task-dot--low'}`} />
          <div>
            <p className={`profile-task-title${task.is_overdue ? ' profile-task-overdue' : ''}`}>{task.title}</p>
            <p className="profile-task-meta">
              {PRIORITY_LABEL[task.priority] ?? `Приоритет ${task.priority}`}
              {task.assignee_team ? ` · ${task.assignee_team}` : ''}
              {task.due_at ? ` · до ${task.due_at}` : ''}
              {task.is_overdue ? ' · просрочено' : ''}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function TabHistory({ decisions, alerts }: { decisions: DecisionItem[]; alerts: AlertItem[] }) {
  const resolved = alerts.filter(a => a.status === 'resolved').slice(0, 5);
  const recent = decisions.slice(0, 10);

  if (recent.length === 0 && resolved.length === 0) {
    return <p className="profile-empty">История пуста</p>;
  }

  return (
    <div className="card">
      {recent.length > 0 && (
        <>
          <p className="profile-kv-title">Последние решения</p>
          {recent.map(d => (
            <div key={d.decision_id} className="profile-history-row">
              <div className="profile-history-dot" />
              <div>
                <p className="profile-history-title">{d.action}</p>
                <p className="profile-history-meta">
                  {d.username}
                  {d.created_at ? ` · ${formatDate(d.created_at)}` : ''}
                  {d.comment ? ` · ${d.comment}` : ''}
                </p>
              </div>
            </div>
          ))}
        </>
      )}
      {resolved.length > 0 && (
        <>
          <p className={`profile-kv-title${recent.length > 0 ? ' profile-kv-title--spaced' : ''}`}>Закрытые алерты</p>
          {resolved.map(a => (
            <div key={a.alert_id} className="profile-history-row">
              <div className="profile-history-dot profile-history-dot--resolved" />
              <div>
                <p className="profile-history-title">{a.title}</p>
                <p className="profile-history-meta">{a.updated_at ? formatDate(a.updated_at) : '—'}</p>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export function ProfileSurface({ objectType, objectId }: { objectType: string; objectId: string }) {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('health');

  useEffect(() => {
    let active = true;
    setError(null);
    setProfile(null);
    fetchProfile(objectType, objectId)
      .then(data => { if (active) setProfile(data); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Ошибка загрузки профиля'); });
    return () => { active = false; };
  }, [objectType, objectId]);

  if (error) return <div className="card">{error}</div>;
  if (!profile) return <div className="card">Загрузка профиля…</div>;

  const { entity, summary, alerts, worklists, decisions, animal_attributes, health_metrics } = profile;
  const recentHealthEvents: HealthEvent[] = profile.recent_health_events ?? [];

  return (
    <div className="grid">
      <AnimalHero
        objectId={entity.object_id}
        attrs={animal_attributes}
        metrics={health_metrics}
        summary={summary}
      />

      {objectType === 'animal' && (
        <>
          <div className="profile-tab-bar">
            {TABS.map(tab => (
              <button
                type="button"
                key={tab.key}
                className={`profile-tab${activeTab === tab.key ? ' profile-tab--active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'health' && (
            <TabHealth metrics={health_metrics} alerts={alerts} events={recentHealthEvents} />
          )}
          {activeTab === 'productivity' && (
            <TabProductivity attrs={animal_attributes} metrics={health_metrics} />
          )}
          {activeTab === 'tasks' && (
            <TabTasks worklists={worklists} />
          )}
          {activeTab === 'history' && (
            <TabHistory decisions={decisions} alerts={alerts} />
          )}
        </>
      )}

      {objectType !== 'animal' && (
        <div className="card">
          <p className="card-title">
            {summary.alerts_open} алерт · {summary.worklists_open} задач · {summary.decisions_total} решений
          </p>
        </div>
      )}
    </div>
  );
}
