import './globals.css';

export const metadata = {
  title: 'GenomeAI Агро',
  description: 'Цифровой зоотехник вашей фермы',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#2dd4bf" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
      </head>
      <body>
        <div className="app-root">{children}</div>
      </body>
    </html>
  );
}
