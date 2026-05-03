// TEMP: preview без auth для визуальной проверки MVP-N01
'use client';

import { AppShell } from '@/components/app/app-shell';

export default function Preview() {
  return (
    <AppShell>
      <div style={{ padding: 40 }}>
        <h1>MVP-N01 UI Preview</h1>
        <p>Проверка Connecterra-style shell без auth</p>
        <p>Дата: {new Date().toLocaleDateString('ru-RU')}</p>
      </div>
    </AppShell>
  );
}
