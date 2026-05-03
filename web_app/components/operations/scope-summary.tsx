import { Card } from '@/components/ui/card';

type ScopeProps = {
  tenantId: string;
  mode?: string;
  activeFarmId?: string | null;
  activeSiteId?: string | null;
  farmCountVisible?: number;
  siteCountVisible?: number;
};

export function ScopeSummary({scope}:{scope:ScopeProps}){return <Card><h3 className="card-title">Область и организация</h3><div className="meta-list"><div className="meta-row"><span>Организация</span><strong>{scope.tenantId}</strong></div><div className="meta-row"><span>Режим</span><strong>{scope.mode}</strong></div><div className="meta-row"><span>Активная ферма</span><strong>{scope.activeFarmId||'все видимые фермы'}</strong></div><div className="meta-row"><span>Активный сайт</span><strong>{scope.activeSiteId||'все видимые сайты'}</strong></div><div className="meta-row"><span>Видимых ферм</span><strong>{scope.farmCountVisible}</strong></div><div className="meta-row"><span>Видимых сайтов</span><strong>{scope.siteCountVisible}</strong></div></div></Card>}
