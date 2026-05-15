import { apiFetch } from '@/lib/api/client';
import type {
  TeamCatalogResponse,
  WorklistCreateRequest,
  WorklistCreateResponse,
} from '@/lib/api/contracts';

export type WorklistValidationError = {
  field: 'title' | 'priority' | 'assignment';
  message: string;
};

export function validateWorklistInput(input: WorklistCreateRequest): WorklistValidationError[] {
  const errors: WorklistValidationError[] = [];
  const title = (input.title || '').trim();
  if (!title) {
    errors.push({ field: 'title', message: 'Заголовок обязателен' });
  }
  const priority = input.priority ?? 3;
  if (!Number.isFinite(priority) || priority < 1 || priority > 5) {
    errors.push({ field: 'priority', message: 'Приоритет должен быть от 1 до 5' });
  }
  const hasTeam = typeof input.assignee_team === 'string' && input.assignee_team.trim() !== '';
  const hasOwner = typeof input.owner_user_id === 'number' && Number.isFinite(input.owner_user_id);
  if (!hasTeam && !hasOwner) {
    errors.push({
      field: 'assignment',
      message: 'Укажите команду или ответственного сотрудника',
    });
  }
  return errors;
}

export async function fetchTeams(): Promise<TeamCatalogResponse> {
  return apiFetch<TeamCatalogResponse>('/api/workflow_v2/teams');
}

export async function createWorklist(input: WorklistCreateRequest): Promise<WorklistCreateResponse> {
  const payload: WorklistCreateRequest = {
    title: input.title.trim(),
    priority: input.priority ?? 3,
  };
  if (input.domain) payload.domain = input.domain;
  if (input.due_at) payload.due_at = input.due_at;
  if (typeof input.owner_user_id === 'number') payload.owner_user_id = input.owner_user_id;
  if (input.assignee_team) payload.assignee_team = input.assignee_team;
  if (input.description) payload.description = input.description;

  return apiFetch<WorklistCreateResponse>('/worklists', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
