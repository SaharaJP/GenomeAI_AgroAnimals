'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Eye, ShieldCheck, Activity, LifeBuoy, KeyRound, Plug, FileText } from 'lucide-react';
import { Card, MetricCard } from '@/components/ui/card';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { fetchExtendedBundle, buildAdminViewModel, type AdminViewModel } from '@/lib/api/extended-surfaces';
import { pathLabels } from '@/lib/navigation';

type Tile = {
  href: string;
  label: string;
  subtitle: string;
  icon: React.ReactNode;
};

const TILES: Tile[] = [
  {
    href: '/admin/iam',
    label: pathLabels['/admin/iam'] || 'IAM-матрица',
    subtitle: 'Просмотр и редактирование привязки ролей к permissions. Каждое изменение фиксируется в audit.',
    icon: <KeyRound size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
  {
    href: '/admin/ai',
    label: pathLabels['/admin/ai'] || 'AI-наблюдаемость',
    subtitle: 'Журнал AI-вызовов, статистика, grounding-rate, отдельные запросы.',
    icon: <Eye size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
  {
    href: '/admin/integrations',
    label: pathLabels['/admin/integrations'] || 'Контроль интеграций',
    subtitle: 'Сводный статус всех интеграций: LLM, batch ingest, IoT, внешние системы.',
    icon: <Plug size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
  {
    href: '/admin/logs',
    label: pathLabels['/admin/logs'] || 'Логи системы',
    subtitle: 'Audit-события из audit_log; фильтр по object_id / action / тексту.',
    icon: <FileText size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
  {
    href: '/observability',
    label: pathLabels['/observability'] || 'Мониторинг',
    subtitle: 'Метрики жизни системы, очереди, длительные операции.',
    icon: <Activity size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
  {
    href: '/readiness',
    label: pathLabels['/readiness'] || 'Готовность системы',
    subtitle: 'Operability/supportability чеки, контур развёртывания.',
    icon: <ShieldCheck size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
  {
    href: '/support',
    label: pathLabels['/support'] || 'Поддержка',
    subtitle: 'Запросы поддержки, диагностика, support-bundle.',
    icon: <LifeBuoy size={20} strokeWidth={1.5} aria-hidden="true" />,
  },
];

export function AdminCommandCenter() {
  const [view, setView] = useState<AdminViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle()
      .then((bundle) => {
        if (active) setView(buildAdminViewModel(bundle));
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Не удалось загрузить admin-сводку');
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="grid">
      <h1 className="page-title">{pathLabels['/admin'] || 'Администрирование'}</h1>
      <p className="page-subtitle">
        Управление IAM-матрицей, AI-наблюдаемость, мониторинг готовности контура и поддержка. Все изменения
        привилегированного характера попадают в audit-журнал.
      </p>

      {error ? (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      ) : null}

      <div className="grid grid-3">
        <MetricCard title="Ролей" value={view?.summary.roleCount ?? '—'} />
        <MetricCard title="Permission-строк" value={view?.summary.permissionRows ?? '—'} />
        <MetricCard title="Readiness-проверок" value={view?.summary.readinessChecks ?? '—'} />
      </div>

      <Card>
        <h3 className="card-title">Точки входа</h3>
        <div className="admin-tiles" role="list">
          {TILES.map((tile) => (
            <Link key={tile.href} href={tile.href} className="admin-tile" role="listitem">
              <span className="admin-tile__icon" aria-hidden="true">
                {tile.icon}
              </span>
              <span className="admin-tile__body">
                <span className="admin-tile__label">{tile.label}</span>
                <span className="admin-tile__subtitle">{tile.subtitle}</span>
              </span>
            </Link>
          ))}
        </div>
      </Card>

      <ExplainabilityBlock
        title="Принципы admin-канона"
        reasons={[
          'RBAC ослаблять нельзя — матрица в src/core/security/, любая правка через UI пишет audit (CLAUDE.md §6).',
          'Admin-страница показывает backend evidence (permission matrix, readiness, audit), а не клиентскую логику.',
          'Каждая плитка — отдельный канонический маршрут; вход в IAM/AI/observability/readiness/support единообразен.',
        ]}
      />
    </div>
  );
}
