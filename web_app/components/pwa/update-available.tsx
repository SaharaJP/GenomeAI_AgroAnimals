'use client';

import { useEffect, useState } from 'react';
import { applySwUpdate } from '@/lib/service-worker-registration';

export function UpdateAvailable() {
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      const { registration: reg } = (e as CustomEvent).detail;
      setRegistration(reg);
    };
    window.addEventListener('sw-update-available', handler);
    return () => window.removeEventListener('sw-update-available', handler);
  }, []);

  if (!registration) return null;

  return (
    <div className="pwa-update-banner" role="alert">
      <span>Доступна новая версия приложения</span>
      <button
        className="pwa-update-btn"
        onClick={() => applySwUpdate(registration)}
      >
        Обновить
      </button>
      <button
        className="pwa-update-dismiss"
        onClick={() => setRegistration(null)}
        aria-label="Закрыть"
      >
        ✕
      </button>
    </div>
  );
}
