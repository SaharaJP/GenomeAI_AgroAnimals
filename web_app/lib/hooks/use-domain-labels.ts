'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api/client';
import type { DomainLabelsResponse } from '@/lib/api/contracts';

const cache = new Map<string, Record<string, string>>();
const inflight = new Map<string, Promise<Record<string, string>>>();

async function fetchLabels(locale: string): Promise<Record<string, string>> {
  const cached = cache.get(locale);
  if (cached) return cached;
  const existing = inflight.get(locale);
  if (existing) return existing;
  const promise = apiFetch<DomainLabelsResponse>(`/catalogs/domain-labels?locale=${encodeURIComponent(locale)}`)
    .then((res) => {
      const map = res?.labels ?? {};
      cache.set(locale, map);
      inflight.delete(locale);
      return map;
    })
    .catch((err) => {
      inflight.delete(locale);
      throw err;
    });
  inflight.set(locale, promise);
  return promise;
}

export function useDomainLabels(locale = 'ru'): {
  labels: Record<string, string>;
  ready: boolean;
  label: (domain: string) => string;
} {
  const cached = cache.get(locale) ?? null;
  const [labels, setLabels] = useState<Record<string, string> | null>(cached);

  useEffect(() => {
    if (cached) return;
    let active = true;
    void fetchLabels(locale)
      .then((map) => { if (active) setLabels(map); })
      .catch(() => { if (active) setLabels({}); });
    return () => { active = false; };
  }, [locale, cached]);

  const resolved = labels ?? {};
  return {
    labels: resolved,
    ready: labels !== null,
    label: (domain: string) => resolved[domain] ?? domain,
  };
}
