'use client';

import { useEffect, useState } from 'react';

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  if (!deferredPrompt || dismissed) return null;

  async function handleInstall() {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') setDeferredPrompt(null);
    else setDismissed(true);
  }

  return (
    <div className="pwa-install-banner" role="complementary" aria-label="Установить приложение">
      <div className="pwa-install-content">
        <span className="pwa-install-icon">🌿</span>
        <div>
          <div className="pwa-install-title">Установить GenomeAI Агро</div>
          <div className="pwa-install-sub">Работает как приложение, доступно офлайн</div>
        </div>
      </div>
      <div className="pwa-install-actions">
        <button className="pwa-install-btn" onClick={handleInstall}>
          Установить
        </button>
        <button
          className="pwa-update-dismiss"
          onClick={() => setDismissed(true)}
          aria-label="Не сейчас"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
