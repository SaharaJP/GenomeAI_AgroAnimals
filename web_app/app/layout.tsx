import './globals.css';
import { SWInit } from '@/components/pwa/sw-init';

export const metadata = {
  title: 'GenomeAI Агро',
  description: 'Цифровой зоотехник вашей фермы',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    title: 'GenomeAI Агро',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
  },
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  minimumScale: 1,
  viewportFit: 'cover',
  themeColor: '#2dd4bf',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-touch-fullscreen" content="yes" />
        <meta name="format-detection" content="telephone=no" />
      </head>
      <body>
        <div className="app-root">{children}</div>
        <SWInit />
      </body>
    </html>
  );
}
