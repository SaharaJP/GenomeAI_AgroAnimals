'use client';

import { createContext, useCallback, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import type { TimelineEvent } from '@/lib/api/timeline';

interface AddEventContextValue {
  isOpen: boolean;
  openDialog: () => void;
  closeDialog: () => void;
  userEvents: TimelineEvent[];
  appendUserEvent: (ev: TimelineEvent) => void;
}

const AddEventContext = createContext<AddEventContextValue | null>(null);

export function AddEventProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [userEvents, setUserEvents] = useState<TimelineEvent[]>([]);

  const openDialog = useCallback(() => setIsOpen(true), []);
  const closeDialog = useCallback(() => setIsOpen(false), []);
  const appendUserEvent = useCallback((ev: TimelineEvent) => {
    setUserEvents((prev) => [ev, ...prev]);
  }, []);

  return (
    <AddEventContext.Provider value={{ isOpen, openDialog, closeDialog, userEvents, appendUserEvent }}>
      {children}
    </AddEventContext.Provider>
  );
}

export function useAddEvent() {
  const ctx = useContext(AddEventContext);
  if (!ctx) throw new Error('useAddEvent must be used inside AddEventProvider');
  return ctx;
}
