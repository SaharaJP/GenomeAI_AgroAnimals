import { apiFetch } from '@/lib/api/client';

export interface OvernightChange {
  text: string;
  evidence_id: string | null;
}

export interface TodayAction {
  action: string;
  priority: 'high' | 'medium' | 'low';
  due: string | null;
  role: 'vet' | 'zootech' | 'operator' | 'director';
}

export interface MorningBrief {
  brief_id: string;
  farm_id: string;
  generated_at_utc: string;
  date: string;
  headline: string;
  main_takeaway: string;
  overnight_changes: OvernightChange[];
  today_actions: TodayAction[];
  notes: string[];
  generation_model: string;
  generation_tokens: { input: number; output: number };
}

export async function fetchMorningBrief(farmId = 'INV_FARM_001'): Promise<MorningBrief> {
  return apiFetch<MorningBrief>(`/api/ai/morning-brief/today?farm_id=${encodeURIComponent(farmId)}`);
}

export async function regenerateMorningBrief(farmId = 'INV_FARM_001'): Promise<MorningBrief> {
  return apiFetch<MorningBrief>('/api/ai/morning-brief', {
    method: 'POST',
    body: JSON.stringify({ farm_id: farmId, force_regenerate: true }),
  });
}

export function morningBriefPdfUrl(briefId: string, farmId = 'INV_FARM_001'): string {
  return `/api/backend/api/ai/morning-brief/${briefId}/pdf?farm_id=${encodeURIComponent(farmId)}`;
}

export interface ApproveBriefResult {
  approved: boolean;
  tasks_created: number;
}

export async function approveMorningBrief(
  briefId: string,
  actions: TodayAction[],
  farmId = 'INV_FARM_001',
): Promise<ApproveBriefResult> {
  return apiFetch<ApproveBriefResult>(`/api/ai/morning-brief/${encodeURIComponent(briefId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ farm_id: farmId, actions }),
  });
}
