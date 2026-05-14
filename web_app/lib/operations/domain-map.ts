// Маппинг страница → workflow domain.
// Канонический список domain id'ов определён в src/core/workflow/policies.py
// (WORKFLOW_DOMAINS). Локализованные подписи — в configs/workflow_v2/domain_labels.yaml,
// читаются через GET /api/app/v1/catalogs/domain-labels (см. useDomainLabels hook).

export const PAGE_DOMAIN_MAP: Record<string, string> = {
  '/vet': 'health',
  '/reproduction': 'repro',
};
