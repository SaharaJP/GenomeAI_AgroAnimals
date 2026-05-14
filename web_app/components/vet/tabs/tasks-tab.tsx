import { TasksByDomainCard } from '@/components/operations/tasks-by-domain-card';
import { PAGE_DOMAIN_MAP } from '@/lib/operations/domain-map';

export function VetTasksTab() {
  return <TasksByDomainCard domain={PAGE_DOMAIN_MAP['/vet']!} />;
}
