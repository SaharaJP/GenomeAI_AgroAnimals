import { apiFetch } from '@/lib/api/client';

export type IamMatrixAction = {
  key: string;
  title: string;
  permissions: string[];
  roles: Record<string, boolean>;
};

export type IamOverrideRow = {
  role: string;
  permission: string;
  effect: 'grant' | 'revoke';
};

export type IamMatrixResponse = {
  version: number;
  actions: IamMatrixAction[];
  overrides?: IamOverrideRow[];
};

export type IamOverrideEffect = 'grant' | 'revoke' | 'clear';

export type IamOverrideResponse = {
  schema: string;
  role: string;
  permission: string;
  effect: IamOverrideEffect;
  effective_permissions_count: number;
};

export async function fetchPermissionMatrix(): Promise<IamMatrixResponse> {
  return apiFetch<IamMatrixResponse>('/api/admin/permission-matrix');
}

export async function patchPermissionOverride(
  role: string,
  permission: string,
  effect: IamOverrideEffect,
): Promise<IamOverrideResponse> {
  return apiFetch<IamOverrideResponse>('/api/admin/permission-matrix', {
    method: 'PATCH',
    body: JSON.stringify({ role, permission, effect }),
  });
}

export function rolesFromMatrix(matrix: IamMatrixResponse): string[] {
  const seen = new Set<string>();
  for (const action of matrix.actions) {
    for (const role of Object.keys(action.roles)) {
      seen.add(role);
    }
  }
  return Array.from(seen).sort((a, b) => a.localeCompare(b, 'ru'));
}
