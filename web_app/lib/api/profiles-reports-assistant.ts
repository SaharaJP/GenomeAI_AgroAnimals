import { apiFetch } from '@/lib/api/client';
import type { DecisionIntelligenceResponse, FeedbackItem, ListResponse, ProfileResponse, ReportsListResponse } from '@/lib/api/contracts';
import { normalizeListResponse } from '@/lib/api/contracts';

export type ProfileExplainabilityReason = {
  title: string;
  detail: string;
  source: 'alert' | 'worklist' | 'decision';
};

export type ProfileViewModel = {
  profile: ProfileResponse;
  explainabilityReasons: ProfileExplainabilityReason[];
  linkageSummary: Array<{ label: string; value: string }>;
};

export type ReportApprovalState = {
  status: string;
  updated_at?: string | null;
  updated_by_username?: string | null;
  comment?: string | null;
};

export function buildProfileViewModel(profile: ProfileResponse): ProfileViewModel {
  const reasons: ProfileExplainabilityReason[] = [];
  for (const alert of profile.alerts) {
    for (const [key, value] of Object.entries(alert.why || {}).slice(0, 3)) {
      reasons.push({ title: String(key), detail: String(value), source: 'alert' });
    }
  }
  for (const task of profile.worklists) {
    for (const [key, value] of Object.entries(task.why || {}).slice(0, 2)) {
      reasons.push({ title: String(key), detail: String(value), source: 'worklist' });
    }
  }
  for (const decision of profile.decisions.slice(0, 3)) {
    if (decision.reason || decision.comment) {
      reasons.push({
        title: decision.action,
        detail: String(decision.reason || decision.comment || 'Decision trail available from backend audit/log linkage.'),
        source: 'decision',
      });
    }
  }
  const entity = profile.entity;
  const firstLinkage = profile.alerts[0]?.linkage || profile.worklists[0]?.linkage || profile.decisions[0]?.linkage;
  const linkageSummary = [
    { label: 'Object type', value: entity.object_type },
    { label: 'Object id', value: entity.object_id },
    { label: 'Farm', value: entity.farm_id || '—' },
    { label: 'Group', value: entity.group_id || '—' },
    { label: 'Data version', value: firstLinkage?.data_version || 'n/a' },
    { label: 'Report version', value: firstLinkage?.report_version || 'n/a' },
    { label: 'Model version', value: firstLinkage?.model_version || 'n/a' },
  ];
  return {
    profile,
    explainabilityReasons: reasons.length ? reasons.slice(0, 8) : [{ title: 'No invented factors', detail: 'React shows only backend-provided why/reason trail for this object.', source: 'decision' }],
    linkageSummary,
  };
}

export async function fetchProfile(objectType: string, objectId: string): Promise<ProfileResponse> {
  return apiFetch<ProfileResponse>(`/profiles/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}`);
}

export async function fetchReportsCatalog(): Promise<ReportsListResponse> {
  return apiFetch<ReportsListResponse>('/reports');
}

export async function fetchDecisionIntelligence(): Promise<DecisionIntelligenceResponse> {
  return apiFetch<DecisionIntelligenceResponse>('/decision-intelligence');
}

export async function fetchFeedbackFeed(): Promise<ListResponse<FeedbackItem> & { metrics?: Record<string, unknown> }> {
  const payload = await apiFetch<ListResponse<FeedbackItem> & { metrics?: Record<string, unknown> }>('/feedback');
  return { ...normalizeListResponse(payload), metrics: payload.metrics };
}
