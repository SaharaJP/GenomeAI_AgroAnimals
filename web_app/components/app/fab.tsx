'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useAddEvent } from './add-event-context';

export function FAB() {
  const { openDialog } = useAddEvent();
  const [pulsing, setPulsing] = useState(false);

  function handleClick() {
    setPulsing(true);
    setTimeout(() => setPulsing(false), 350);
    openDialog();
  }

  return (
    <button
      className={`fab${pulsing ? ' fab--pulse' : ''}`}
      onClick={handleClick}
      aria-label="Добавить событие"
      title="Добавить событие"
    >
      <Plus size={24} strokeWidth={2} />
    </button>
  );
}
