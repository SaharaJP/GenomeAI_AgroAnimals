import { apiFetch } from '@/lib/api/client';

export interface EconomicsPeriod {
  date_from: string;
  date_to: string;
}

export interface EconomicsScope {
  tenant_id: string;
  level: 'farm' | 'site' | 'pen';
  period: EconomicsPeriod;
  farm_id: string | null;
  site_id: string | null;
  pen_id: string | null;
  data_version: string | null;
  economics_run: string | null;
}

export interface EconomicsTrendDelta {
  margin_per_cow_per_day_pct: number | null;
  total_margin_pct: number | null;
  cost_per_liter_pct: number | null;
  margin_pct_points: number | null;
}

export interface EconomicsKpi {
  margin_per_cow_per_day_rub: number | null;
  total_margin_rub: number | null;
  cost_per_liter_rub: number | null;
  margin_pct: number | null;
  trend_vs_prev_period: EconomicsTrendDelta;
}

export interface EconomicsRevenue {
  milk_rub: number;
  cull_rub: number;
  total_rub: number;
}

export interface EconomicsCost {
  feed_rub: number;
  vet_rub: number;
  repro_rub: number;
  cull_rub: number;
  other_rub: number;
  total_rub: number;
  breakdown_pct: Record<string, number>;
}

export interface EconomicsPerCowDay {
  revenue_rub: number | null;
  cost_rub: number | null;
  margin_rub: number | null;
}

export interface EconomicsSensitivity {
  milk_price_floor_rub_per_kg: number | null;
  feed_cost_ceiling_rub_per_kg_dm: number | null;
  vet_cost_ceiling_rub_per_event: number | null;
  method: string;
}

export interface EconomicsUnitLadder {
  top_quartile_margin_rub: number | null;
  median_margin_rub: number | null;
  bottom_decile_margin_rub: number | null;
  bottom_decile_cohort_n: number | null;
  bottom_decile_cohort_ref: string | null;
}

export interface EconomicsRoiAction {
  action_id: string;
  label: string;
  cohort_n: number;
  window_days: number;
  delta_margin_per_cow_day_rub: number | null;
  total_margin_delta_rub: number | null;
  method: string;
}

export interface EconomicsStrategicKpi {
  roi_per_cow_per_year_pct: number | null;
  roi_per_cow_lifetime_pct: number | null;
  payback_months: number | null;
  ltv_cac_ratio: number | null;
  acquisition_cost_rub_per_cow: number | null;
  saas_cac_rub: number | null;
  lifetime_years: number | null;
  retention_months: number | null;
}

export interface EconomicsScenariosSummary {
  total: number;
  approved: number;
  draft: number;
  archived: number;
  open_at: string;
}

export interface EconomicsAiCostCalls {
  morning_brief_avg_rub: number | null;
  weekly_brief_avg_rub: number | null;
  ask_farm_avg_rub: number | null;
}

export interface EconomicsAiCost {
  period_rub: number | null;
  per_cow_per_year_rub: number | null;
  calls: EconomicsAiCostCalls;
}

export interface EconomicsSummaryResponse {
  schema: string;
  scope: EconomicsScope;
  kpi: EconomicsKpi;
  revenue: EconomicsRevenue;
  cost: EconomicsCost;
  per_cow_day: EconomicsPerCowDay;
  sensitivity: EconomicsSensitivity;
  unit_economics_ladder: EconomicsUnitLadder;
  roi_actions: EconomicsRoiAction[];
  strategic_kpi: EconomicsStrategicKpi;
  scenarios_summary: EconomicsScenariosSummary;
  ai_cost: EconomicsAiCost | null;
  formula_refs: Record<string, string>;
  warnings: string[];
}

export interface EconomicsSummaryQuery {
  data_version: string;
  level?: 'farm' | 'site' | 'pen';
  period_from?: string;
  period_to?: string;
  farm_id?: string;
  site_id?: string;
  pen_id?: string;
  economics_run?: string;
  cows_total?: number;
}

export function fetchEconomicsSummary(query: EconomicsSummaryQuery): Promise<EconomicsSummaryResponse> {
  const params = new URLSearchParams();
  params.set('data_version', query.data_version);
  if (query.level) params.set('level', query.level);
  if (query.period_from) params.set('period_from', query.period_from);
  if (query.period_to) params.set('period_to', query.period_to);
  if (query.farm_id) params.set('farm_id', query.farm_id);
  if (query.site_id) params.set('site_id', query.site_id);
  if (query.pen_id) params.set('pen_id', query.pen_id);
  if (query.economics_run) params.set('economics_run', query.economics_run);
  if (typeof query.cows_total === 'number') params.set('cows_total', String(query.cows_total));
  const qs = params.toString();
  return apiFetch<EconomicsSummaryResponse>(`/economics/summary${qs ? `?${qs}` : ''}`);
}
