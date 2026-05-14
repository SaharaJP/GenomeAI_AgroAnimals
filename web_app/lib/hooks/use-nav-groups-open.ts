'use client';

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'nav.groups.open';

function readStorage(): Set<string> {
  if (typeof window === 'undefined') return new Set<string>();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set<string>();
    const arr: unknown = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set<string>();
    return new Set<string>(arr.filter((x): x is string => typeof x === 'string'));
  } catch {
    return new Set<string>();
  }
}

function writeStorage(open: Set<string>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...open]));
  } catch {
    // ignore quota/privacy errors
  }
}

export type UseNavGroupsOpen = {
  isOpen: (label: string) => boolean;
  toggle: (label: string) => void;
};

export function useNavGroupsOpen(autoOpenLabels: readonly string[] = []): UseNavGroupsOpen {
  const [storedOpen, setStoredOpen] = useState<Set<string>>(() => new Set<string>());

  useEffect(() => {
    setStoredOpen(readStorage());
  }, []);

  const isOpen = useCallback(
    (label: string) => autoOpenLabels.includes(label) || storedOpen.has(label),
    [storedOpen, autoOpenLabels],
  );

  const toggle = useCallback((label: string) => {
    setStoredOpen((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      writeStorage(next);
      return next;
    });
  }, []);

  return { isOpen, toggle };
}
