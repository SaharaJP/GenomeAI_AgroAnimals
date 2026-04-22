import Link from 'next/link';

export default function TimelinePage() {
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link href="/dashboard" style={{ fontSize: 13, color: 'var(--accent-text)' }}>
          ← Назад к обзору
        </Link>
      </div>
      <h1 className="page-title">Лента событий</h1>
      <p className="page-subtitle">Полная история событий на ферме — страница в разработке.</p>
      <div className="card" style={{ marginTop: 20 }}>
        <div className="empty-state">
          Полная лента событий с фильтрацией и поиском появится в следующих версиях.<br />
          <Link href="/daily-summary" style={{ color: 'var(--accent-text)' }}>
            Перейти к ежедневной сводке →
          </Link>
        </div>
      </div>
    </div>
  );
}
