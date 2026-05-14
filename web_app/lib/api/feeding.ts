import { apiFetch } from '@/lib/api/client';
import type { FeedingRationsResponse, FeedIntakeDropsResponse } from './contracts';

export function getFeedingRations(): Promise<FeedingRationsResponse> {
  return apiFetch<FeedingRationsResponse>('/feeding/rations');
}

export function getFeedIntakeDrops(): Promise<FeedIntakeDropsResponse> {
  return apiFetch<FeedIntakeDropsResponse>('/feeding/intake-drops');
}
