import { apiFetch } from '@/lib/api/client';
import { getBrowserAppConfig } from '@/lib/config';
import type {
  Personnel,
  PersonnelCreateRequest,
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

export function validatePersonnelCreate(body: PersonnelCreateRequest): PersonnelValidationError[] {
  const errs: PersonnelValidationError[] = [];
  if (!(body.full_name || '').trim()) {
    errs.push({ field: 'full_name', message: 'ФИО обязательно' });
  }
  if (!(body.position || '').trim()) {
    errs.push({ field: 'position', message: 'Должность обязательна' });
  }
  if (body.email && body.email.trim() !== '' && !body.email.includes('@')) {
    errs.push({ field: 'email', message: 'Некорректный email' });
  }
  return errs;
}

export async function createPersonnel(body: PersonnelCreateRequest): Promise<PersonnelResponse> {
  return apiFetch<PersonnelResponse>(`/personnel`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export type PersonnelPhotoUploadResponse = {
  personnel_id: string;
  photo_ref: string;
  size_bytes: number;
};

export type PersonnelPhotoUrlResponse = {
  personnel_id: string;
  url: string;
  expires_in: number;
};

export async function uploadPersonnelPhoto(
  personnelId: string,
  file: File,
): Promise<PersonnelPhotoUploadResponse> {
  const config = getBrowserAppConfig();
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(
    `${config.backendProxyBasePath}/personnel/${encodeURIComponent(personnelId)}/photo`,
    {
      method: 'POST',
      credentials: 'include',
      cache: 'no-store',
      body: formData,
    },
  );
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail?.detail) msg = String(body.detail.detail);
    } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<PersonnelPhotoUploadResponse>;
}

export async function getPersonnelPhotoUrl(personnelId: string): Promise<PersonnelPhotoUrlResponse | null> {
  try {
    return await apiFetch<PersonnelPhotoUrlResponse>(
      `/personnel/${encodeURIComponent(personnelId)}/photo`,
    );
  } catch {
    return null;
  }
}

export async function deletePersonnelPhoto(personnelId: string): Promise<void> {
  const config = getBrowserAppConfig();
  const res = await fetch(
    `${config.backendProxyBasePath}/personnel/${encodeURIComponent(personnelId)}/photo`,
    { method: 'DELETE', credentials: 'include', cache: 'no-store' },
  );
  if (!res.ok && res.status !== 204) {
    throw new Error(`HTTP ${res.status}`);
  }
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
