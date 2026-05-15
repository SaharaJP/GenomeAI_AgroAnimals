import { apiFetch } from '@/lib/api/client';

export type IntegrationStatus = 'ok' | 'degraded' | 'down' | 'disabled';

export type IntegrationKind =
  | 'llm'
  | 'batch_connector'
  | 'iot_device'
  | 'external_system'
  | 'sensor_ingestion';

export type IntegrationHealth = {
  id: string;
  name: string;
  kind: IntegrationKind;
  status: IntegrationStatus;
  last_sync_at?: string | null;
  records_in_last_window?: number | null;
  error_count?: number | null;
  last_error?: string | null;
  latency_ms?: number | null;
  note?: string | null;
};

export type IntegrationsHealthResponse = {
  schema: string;
  items: IntegrationHealth[];
  total: number;
};

export async function fetchIntegrationsHealth(): Promise<IntegrationsHealthResponse> {
  return apiFetch<IntegrationsHealthResponse>('/integrations/health');
}

export const KIND_LABELS: Record<IntegrationKind, string> = {
  llm: 'LLM',
  batch_connector: 'Batch ingest',
  iot_device: 'IoT-устройства',
  external_system: 'Внешние системы',
  sensor_ingestion: 'Sensor ingestion',
};

export const STATUS_LABELS: Record<IntegrationStatus, string> = {
  ok: 'Работает',
  degraded: 'Деградация',
  down: 'Недоступно',
  disabled: 'Отключено',
};
