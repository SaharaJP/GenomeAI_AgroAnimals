import { SupportGovernanceSurface } from '@/components/extended/support-governance-surface';

export default async function SupportPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  return (
    <div className="grid">
      <div className="topbar"><div><h1 className="page-title">Support / governance</h1><p className="page-subtitle">Support, diagnostics, release and governance surface for office and admin users.</p></div></div>
      <SupportGovernanceSurface hookContext={params} />
    </div>
  );
}
