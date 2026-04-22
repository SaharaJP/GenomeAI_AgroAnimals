import Link from 'next/link';

export default function AnalyticsPage() {
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link href="/dashboard" style={{ fontSize: 13, color: 'var(--accent-text)' }}>
          ← Назад к обзору
        </Link>
      </div>
      <h1 className="page-title">Аналитика</h1>
      <p className="page-subtitle">Панели аналитики по показателям стада — страница в разработке.</p>
      <div className="card" style={{ marginTop: 20 }}>
        <div className="empty-state">
          Интерактивные графики и панели аналитики появятся в следующих версиях.<br />
          <Link href="/economics" style={{ color: 'var(--accent-text)' }}>
            Перейти к экономике →
          </Link>
        </div>
      </div>
    </div>
  );
}
