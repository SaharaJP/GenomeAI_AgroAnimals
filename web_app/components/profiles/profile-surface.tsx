'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, MetricCard } from '@/components/ui/card';
import { AlertList } from '@/components/operations/alert-list';
import { WorklistList } from '@/components/ui/worklist-list';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { SourceLinkagePanel } from '@/components/explainability/source-linkage-panel';
import { ObjectExplainabilityPanel } from '@/components/explainability/object-explainability-panel';
import { AssistantEntryPoints } from '@/components/assistant/assistant-entry-points';
import { DecisionIntelligenceWidgets } from '@/components/decision/decision-intelligence-widgets';
import { buildProfileViewModel, fetchDecisionIntelligence, fetchProfile, type ProfileViewModel } from '@/lib/api/profiles-reports-assistant';
import type { DecisionIntelligenceResponse } from '@/lib/api/contracts';

export function ProfileSurface({ objectType, objectId }: { objectType: string; objectId: string }) {
  const [profile, setProfile] = useState<ProfileViewModel | null>(null);
  const [decisionIntel, setDecisionIntel] = useState<DecisionIntelligenceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setError(null);
    void Promise.all([fetchProfile(objectType, objectId), fetchDecisionIntelligence()])
      .then(([profilePayload, decisionPayload]) => {
        if (!active) return;
        setProfile(buildProfileViewModel(profilePayload));
        setDecisionIntel(decisionPayload);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load profile surface');
      });
    return () => {
      active = false;
    };
  }, [objectId, objectType]);

  const title = objectType === 'animal' ? 'Animal Profile' : objectType === 'group' ? 'Group Profile' : 'Object Profile';

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">{title}</h1>
          <p className="page-subtitle">React profile surface with source linkage, object explainability and linked actions. Backend-linked object context with explainability and linked actions.</p>
        </div>
      </div>
      <FactPackGuardrailNote />
      {error ? <div className="card error-text">{error}</div> : null}
      {!profile ? <div className="card">Loading profile…</div> : (
        <>
          <div className="grid grid-3">
            <MetricCard title="Open alerts" value={profile.profile.summary.alerts_open} />
            <MetricCard title="Open worklists" value={profile.profile.summary.worklists_open} />
            <MetricCard title="Decisions" value={profile.profile.summary.decisions_total} />
          </div>
          <div className="grid grid-2">
            <SourceLinkagePanel items={profile.linkageSummary} />
            <AssistantEntryPoints
              objectType={profile.profile.entity.object_type}
              objectId={profile.profile.entity.object_id}
              dataVersion={profile.profile.alerts[0]?.linkage?.data_version || profile.profile.worklists[0]?.linkage?.data_version || null}
              reportVersion={profile.profile.alerts[0]?.linkage?.report_version || profile.profile.decisions[0]?.linkage?.report_version || null}
              contextLabel="profile"
            />
          </div>
          <ObjectExplainabilityPanel reasons={profile.explainabilityReasons} />
          <Card>
            <h3 className="card-title">Linked actions</h3>
            <div className="linked-inline-actions">
              <Link href={`/assistant?target=profile&object_type=${encodeURIComponent(profile.profile.entity.object_type)}&object_id=${encodeURIComponent(profile.profile.entity.object_id)}`}>Explain in assistant</Link>
              <Link href={`/decisions?object_id=${encodeURIComponent(profile.profile.entity.object_id)}`}>Decision hook</Link>
              <Link href={`/support?object_id=${encodeURIComponent(profile.profile.entity.object_id)}`}>Feedback hook</Link>
              <Link href="/reports">Open related reports</Link>
            </div>
          </Card>
          <div className="grid grid-2">
            <div>
              <h2 className="section-title">Linked alerts</h2>
              <AlertList items={profile.profile.alerts.slice(0, 8)} />
            </div>
            <div>
              <h2 className="section-title">Linked worklists</h2>
              <WorklistList items={profile.profile.worklists.slice(0, 8)} />
            </div>
          </div>
          {decisionIntel ? <DecisionIntelligenceWidgets data={decisionIntel} /> : null}
        </>
      )}
    </div>
  );
}
