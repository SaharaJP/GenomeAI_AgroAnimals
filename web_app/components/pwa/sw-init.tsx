'use client';

import { useEffect } from 'react';
import { registerServiceWorker } from '@/lib/service-worker-registration';

export function SWInit() {
  useEffect(() => {
    registerServiceWorker();
  }, []);

  return null;
}
