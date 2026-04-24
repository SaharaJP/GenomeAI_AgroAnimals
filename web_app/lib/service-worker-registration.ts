const SW_PATH = '/sw.js';

export function registerServiceWorker(): void {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(SW_PATH, { scope: '/' })
      .then((registration) => {
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          if (!newWorker) return;

          newWorker.addEventListener('statechange', () => {
            if (
              newWorker.state === 'installed' &&
              navigator.serviceWorker.controller
            ) {
              window.dispatchEvent(
                new CustomEvent('sw-update-available', { detail: { registration } }),
              );
            }
          });
        });
      })
      .catch(() => {
        // SW registration is best-effort; non-fatal
      });
  });
}

export function applySwUpdate(registration: ServiceWorkerRegistration): void {
  if (!registration.waiting) return;
  registration.waiting.postMessage('SKIP_WAITING');
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload();
  });
}
