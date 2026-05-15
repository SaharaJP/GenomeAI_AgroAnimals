import { apiFetch } from '@/lib/api/client';
import { getBrowserAppConfig } from '@/lib/config';
import type {
  PersonnelResponse,
  PersonnelUpdateRequest,
} from '@/lib/api/contracts';

export type PersonnelEditableField = keyof PersonnelUpdateRequest;

export type PersonnelValidationError = {
  field: PersonnelEditableField;
  message: string;
};

export function validatePersonnelUpdate(patch: PersonnelUpdateRequest): PersonnelValidationError[] {
  const errs: PersonnelValidationError[] = [];
  if (patch.full_name !== undefined && patch.full_name !== null && !(patch.full_name || '').trim()) {
    errs.push({ field: 'full_name', message: 'ФИО не может быть пустым' });
  }
  if (patch.position !== undefined && patch.position !== null && !(patch.position || '').trim()) {
    errs.push({ field: 'position', message: 'Должность не может быть пустой' });
  }
  if (patch.email !== undefined && patch.email && patch.email.trim() !== '' && !patch.email.includes('@')) {
    errs.push({ field: 'email', message: 'Некорректный email' });
  }
  return errs;
}

export function buildPersonnelPatch(
  initial: PersonnelUpdateRequest,
  next: PersonnelUpdateRequest,
): PersonnelUpdateRequest {
  const patch: PersonnelUpdateRequest = {};
  (Object.keys(next) as PersonnelEditableField[]).forEach((field) => {
    const a = initial[field];
    const b = next[field];
    const norm = (v: unknown) => (typeof v === 'string' ? v.trim() : v ?? null);
    if (norm(a) !== norm(b)) {
      patch[field] = b as never;
    }
  });
  return patch;
}

export async function updatePersonnel(
  personnelId: string,
  patch: PersonnelUpdateRequest,
): Promise<PersonnelResponse> {
  return apiFetch<PersonnelResponse>(`/personnel/${encodeURIComponent(personnelId)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export async function deletePersonnel(personnelId: string): Promise<void> {
  const config = getBrowserAppConfig();
  const response = await fetch(
    `${config.backendProxyBasePath}/personnel/${encodeURIComponent(personnelId)}`,
    { method: 'DELETE', credentials: 'include', cache: 'no-store' },
  );
  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = String(body.detail);
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}
