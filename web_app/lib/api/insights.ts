export type InsightStatus = 'to_check' | 'to_follow_up' | 'done';
export type InsightSeverity = 'urgent' | 'high' | 'warn' | 'info';

export type InsightRecommendation = {
  id: string;
  text: string;
  deadline?: string;
};

export type InsightItem = {
  insight_id: string;
  type: string;
  severity: InsightSeverity;
  status: InsightStatus;
  date: string;
  animal_ids: string[];
  title: string;
  body: string;
  action: string;
  tags: string[];
  farmPct?: number;
  holdingPct?: number;
  chartData?: number[];
  chartLabel?: string;
  chartUnit?: string;
  recommendations?: InsightRecommendation[];
  edited_at?: string | null;
};

export const INSIGHT_STATUS_LABELS: Record<InsightStatus, string> = {
  to_check: 'К проверке',
  to_follow_up: 'В работе',
  done: 'Закрыто',
};

export const SEVERITY_BADGE: Record<InsightSeverity, string> = {
  urgent: 'badge-danger',
  high: 'badge-warning',
  warn: 'badge-warning',
  info: 'badge-info',
};

export const SEVERITY_LABEL: Record<InsightSeverity, string> = {
  urgent: 'Срочно',
  high: 'Высокий',
  warn: 'Предупреждение',
  info: 'Инфо',
};

export function formatRuDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}
