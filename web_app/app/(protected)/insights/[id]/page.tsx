import Link from 'next/link';

export default function InsightDetailPage({ params }: { params: { id: string } }) {
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link href="/dashboard" style={{ fontSize: 13, color: 'var(--accent-text)' }}>
          ← Назад к обзору
        </Link>
      </div>
      <h1 className="page-title">Инсайт {params.id}</h1>
      <p className="page-subtitle">Детальный просмотр инсайта — страница в разработке.</p>
      <div className="card" style={{ marginTop: 20 }}>
        <div className="empty-state">
          Подробная карточка инсайта появится в следующих версиях.<br />
          <Link href="/decisions" style={{ color: 'var(--accent-text)' }}>
            Перейти в рекомендации →
          </Link>
        </div>
      </div>
    </div>
  );
}
