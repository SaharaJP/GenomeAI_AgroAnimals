import Link from 'next/link';
import type { DailyBriefPreviewModel } from '@/lib/api/daily-operations';
import { Card } from '@/components/ui/card';

export function DailyBriefPreview({brief}:{brief:DailyBriefPreviewModel}){return <Card><h3 className="card-title">Daily brief preview</h3><p className="card-subtitle">{brief.headline}</p><div className="brief-status">{brief.statusLine}</div><ul className="bullet-list">{(Array.isArray(brief?.bullets) ? brief.bullets : []).map(item=><li key={item}>{item}</li>)}</ul><div className="linked-actions-grid">{(Array.isArray(brief?.actions) ? brief.actions : []).map(action=><Link className="linked-action-card" href={action.href} key={action.href}><div className="linked-action-count">{action.count}</div><div><div className="linked-action-title">{action.label}</div><div className="linked-action-caption">{action.caption}</div></div></Link>)}</div></Card>}


export function buildDailyBriefPreview(bundle: any) {
  try {
    const planner = bundle?.planner ?? {};
    const summary = planner?.summary ?? {};
    const worklists = bundle?.worklists ?? {};
    const feedback = bundle?.feedback ?? {};

    const alertsNew = Number(summary?.alerts_new ?? 0);
    const alertsAck = Number(summary?.alerts_acknowledged ?? 0);
    const alertsResolved = Number(summary?.alerts_resolved ?? 0);
    const tasksOpen = Number(summary?.tasks_open ?? worklists?.total ?? 0);
    const tasksDone = Number(summary?.tasks_done ?? 0);
    const overdueActive = Number(summary?.overdue_active ?? 0);
    const pendingApprovals = Number(planner?.pending_approvals ?? 0);
    const acceptanceRate = Number(feedback?.metrics?.acceptance_rate ?? 0);

    const headline = `Open tasks: ${tasksOpen}. Active alerts: ${alertsNew + alertsAck}. Overdue: ${overdueActive}.`;
    const whyNow = pendingApprovals > 0
      ? `Ожидают подтверждения: ${pendingApprovals}.`
      : "Планировщик доступен, блокирующих подтверждений не обнаружено.";

    return { bullets: [], links: [],
      title: "Сводка дня",
      heading: "Сводка дня",
      summary: headline,
      primaryMessage: headline,
      primary_message: headline,
      whyNow,
      why_now: whyNow,
      facts: [
        { key: "tasks_open", label: "Открытых задач", value: String(tasksOpen) },
        { key: "alerts_active", label: "Активных алертов", value: String(alertsNew + alertsAck) },
        { key: "overdue_active", label: "Просроченных", value: String(overdueActive) },
        { key: "acceptance_rate", label: "Принятие рекомендаций", value: `${Math.round(acceptanceRate * 100)}%` },
      ],
      keyFacts: [
        { key: "tasks_open", label: "Открытых задач", value: String(tasksOpen) },
        { key: "alerts_active", label: "Активных алертов", value: String(alertsNew + alertsAck) },
        { key: "alerts_resolved", label: "Решённых алертов", value: String(alertsResolved) },
        { key: "tasks_done", label: "Выполненных задач", value: String(tasksDone) },
        { key: "overdue_active", label: "Просроченных", value: String(overdueActive) },
      ],
      actions: [],
      suggestedActions: [],
      suggested_actions: [],
    };
  } catch {
    return {
      title: "Сводка дня",
      heading: "Сводка дня",
      summary: "Планировщик открыт успешно.",
      primaryMessage: "Планировщик открыт успешно.",
      primary_message: "Планировщик открыт успешно.",
      whyNow: "Резервный построитель сводки активен.",
      why_now: "Резервный построитель сводки активен.",
      facts: [],
      keyFacts: [],
      actions: [],
      suggestedActions: [],
      suggested_actions: [],
    };
  }
}
