import { apiFetch } from '@/lib/api/client';

export interface WeeklyBriefPeriod {
  start: string;
  end: string;
}

export interface BriefSection {
  heading: string;
  narrative: string;
  highlights: string[];
  evidence_ids: string[];
}

export interface KeyRecommendation {
  recommendation: string;
  priority: 'high' | 'medium' | 'low';
  rationale: string;
  expected_outcome: string;
  affected_entities: string[];
}

export interface WeeklyAnomaly {
  description: string;
  severity: 'critical' | 'warning' | 'info';
  evidence_id: string;
}

export interface KpiEntry {
  value: number;
  prev_period: number | null;
  delta_pct: number | null;
  unit: string;
}

export interface WeeklyBrief {
  brief_id: string;
  farm_id: string;
  period: WeeklyBriefPeriod;
  generated_at_utc: string;
  title: string;
  executive_summary: string;
  sections: BriefSection[];
  key_recommendations: KeyRecommendation[];
  anomalies_detected: WeeklyAnomaly[];
  kpi_table: Record<string, KpiEntry>;
  generation_model: string;
  generation_tokens: { input: number; output: number };
}

export async function fetchWeeklyBrief(farmId = 'INV_FARM_001'): Promise<WeeklyBrief> {
  return apiFetch<WeeklyBrief>(
    `/api/ai/weekly-brief/latest?farm_id=${encodeURIComponent(farmId)}`,
  );
}

export async function generateWeeklyBrief(
  farmId = 'INV_FARM_001',
  startDate?: string,
  endDate?: string,
): Promise<WeeklyBrief> {
  return apiFetch<WeeklyBrief>('/api/ai/weekly-brief', {
    method: 'POST',
    body: JSON.stringify({
      farm_id: farmId,
      start_date: startDate ?? '',
      end_date: endDate ?? '',
      force_regenerate: true,
    }),
  });
}

export function weeklyBriefPdfUrl(briefId: string, farmId = 'INV_FARM_001'): string {
  return `/api/backend/api/ai/weekly-brief/${briefId}/pdf?farm_id=${encodeURIComponent(farmId)}`;
}
