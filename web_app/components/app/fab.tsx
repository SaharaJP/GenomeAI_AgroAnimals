'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';

export function FAB() {
  const [visible, setVisible] = useState(false);

  function handleClick() {
    setVisible(true);
    setTimeout(() => setVisible(false), 3000);
  }

  return (
    <>
      <button
        className="fab"
        onClick={handleClick}
        aria-label="Добавить событие"
        title="Добавить событие"
      >
        <Plus size={24} strokeWidth={2} />
      </button>

      {visible && (
        <div className="toast" role="status" aria-live="polite">
          Форма в разработке
        </div>
      )}
    </>
  );
}
