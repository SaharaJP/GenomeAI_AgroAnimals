import { apiFetch } from '@/lib/api/client';

export type ImpactInterpretation = 'positive' | 'negative' | 'neutral' | 'mixed';
export type ImpactSignificance = 'major' | 'moderate' | 'minor' | 'insignificant';
export type ImpactWindow = '3d' | '1w' | '2w' | '4w';

export interface ImpactNarrative {
  event_id: string;
  window: string;
  narrative: string;
  interpretation: ImpactInterpretation;
  significance: ImpactSignificance;
  recommendations: string[];
  confidence: number;
  generation_model: string;
  generated_at: string;
}

export interface ImpactNarrativeRequest {
  event_id: string;
  window?: ImpactWindow;
  language?: string;
  farm_id?: string;
}

export async function fetchImpactNarrative(req: ImpactNarrativeRequest): Promise<ImpactNarrative> {
  return apiFetch<ImpactNarrative>('/api/ai/impact-narrative', {
    method: 'POST',
    body: JSON.stringify({
      event_id: req.event_id,
      window: req.window ?? '1w',
      language: req.language ?? 'ru',
      farm_id: req.farm_id ?? 'demo-farm-v1',
    }),
  });
}
