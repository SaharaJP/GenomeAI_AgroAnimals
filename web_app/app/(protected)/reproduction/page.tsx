import { ReproductionSurface } from '@/components/extended/reproduction-surface';
import { TasksByDomainCard } from '@/components/operations/tasks-by-domain-card';
import { PAGE_DOMAIN_MAP } from '@/lib/operations/domain-map';

export default function ReproductionPage() {
  return (
    <>
      <ReproductionSurface />
      <div style={{ marginTop: 16 }}>
        <TasksByDomainCard domain={PAGE_DOMAIN_MAP['/reproduction']!} />
      </div>
    </>
  );
}
