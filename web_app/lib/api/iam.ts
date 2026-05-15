import { apiFetch } from '@/lib/api/client';

export type IamMatrixAction = {
  key: string;
  title: string;
  permissions: string[];
  roles: Record<string, boolean>;
};

export type IamMatrixResponse = {
  version: number;
  actions: IamMatrixAction[];
};

export async function fetchPermissionMatrix(): Promise<IamMatrixResponse> {
  return apiFetch<IamMatrixResponse>('/api/admin/permission-matrix');
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
