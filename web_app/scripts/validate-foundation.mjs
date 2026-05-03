import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const mustExist = [
  'app/layout.tsx',
  'app/(protected)/layout.tsx',
  'app/(protected)/daily-summary/page.tsx',
  'app/(protected)/alerts/page.tsx',
  'app/(protected)/worklists/page.tsx',
  'app/(protected)/planner/page.tsx',
  'app/(protected)/reproduction/page.tsx',
  'app/(protected)/vet/page.tsx',
  'app/(protected)/treatments/page.tsx',
  'app/(protected)/economics/page.tsx',
  'app/(protected)/support/page.tsx',
  'app/(protected)/pilot/page.tsx',
  'app/(protected)/readiness/page.tsx',
  'app/(protected)/observability/page.tsx',
  'app/(protected)/admin/page.tsx',
  'app/(protected)/profiles/[objectType]/[objectId]/page.tsx',
  'app/(protected)/reports/[dataVersion]/[reportVersion]/page.tsx',
  'components/app/app-shell.tsx',
  'components/operations/daily-operations-dashboard.tsx',
  'components/profiles/profile-surface.tsx',
  'components/reports/report-view-surface.tsx',
  'components/extended/reproduction-surface.tsx',
  'components/extended/vet-queues-surface.tsx',
  'components/extended/treatments-withdrawal-surface.tsx',
  'components/extended/economics-master-surface.tsx',
  'components/extended/support-governance-surface.tsx',
  'components/extended/pilot-readiness-surface.tsx',
  'components/extended/admin-command-center.tsx',
  'components/extended/observability-surface.tsx',
  'lib/api/client.ts',
  'lib/api/daily-operations.ts',
  'lib/api/profiles-reports-assistant.ts',
  'lib/api/extended-surfaces.ts',
  'app/api/backend/[...path]/route.ts',
  'app/api/report-governance/[dataVersion]/[reportVersion]/route.ts',
  'app/api/admin/permission-matrix/route.ts',
  'app/api/observability/route.ts',
];

for (const rel of mustExist) {
  if (!existsSync(join(root, rel))) throw new Error(`Missing web_app file: ${rel}`);
}

const client = readFileSync(join(root, 'lib/api/client.ts'), 'utf8');
const proxy = readFileSync(join(root, 'app/api/backend/[...path]/route.ts'), 'utf8');
const navigation = readFileSync(join(root, 'lib/navigation.ts'), 'utf8');
const reproduction = readFileSync(join(root, 'components/extended/reproduction-surface.tsx'), 'utf8');
const admin = readFileSync(join(root, 'components/extended/admin-command-center.tsx'), 'utf8');

if (!client.includes('backendProxyBasePath')) throw new Error('API client is not wired to backend proxy');
if (!proxy.includes('/api/app/v1/')) throw new Error('Backend proxy is not wired to canonical API boundary');
for (const route of ['/reproduction', '/vet', '/treatments', '/economics', '/support', '/pilot', '/readiness', '/observability', '/admin']) {
  if (!navigation.includes(route)) throw new Error(`Navigation missing route ${route}`);
}
if (!reproduction.includes('No reproduction logic is reimplemented in the browser')) {
  throw new Error('Reproduction parity note missing backend-first posture');
}
if (!admin.includes('backend evidence')) {
  throw new Error('Admin surface is missing backend-evidence posture');
}
console.log('web_app T32-07 validation OK');
