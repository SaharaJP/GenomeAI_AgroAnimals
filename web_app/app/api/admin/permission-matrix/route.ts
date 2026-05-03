import { NextResponse } from 'next/server';
import { backendFetch, clearAuthCookies, getAuthTokens, refreshAccessToken, setAuthCookies } from '@/lib/server/backend';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

async function readJsonBody(response: Response): Promise<Record<string, unknown>> {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    const parsed = JSON.parse(text);
    return isRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function normalizePermissionMatrix(body: Record<string, unknown>): Record<string, unknown> {
  if (Array.isArray(body.rows)) {
    return body;
  }

  const actions = Array.isArray(body.actions)
    ? body.actions.filter(isRecord)
    : [];

  const rows: Array<{ role: string; permission: string; source: string }> = [];

  for (const action of actions) {
    const source =
      (typeof action.title === 'string' && action.title.trim()) ||
      (typeof action.key === 'string' && action.key.trim()) ||
      'permission_matrix';

    const permissions = Array.isArray(action.permissions)
      ? action.permissions.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      : [];

    const roles = isRecord(action.roles) ? action.roles : {};
    const enabledRoles = Object.entries(roles)
      .filter(([, enabled]) => Boolean(enabled))
      .map(([role]) => role);

    if (permissions.length === 0) {
      for (const role of enabledRoles) {
        rows.push({ role, permission: '—', source: String(source) });
      }
      continue;
    }

    for (const role of enabledRoles) {
      for (const permission of permissions) {
        rows.push({
          role,
          permission,
          source: String(source),
        });
      }
    }
  }

  return { ...body, rows };
}

export async function GET() {
  const { accessToken, refreshToken } = await getAuthTokens();
  const attempt = (token?: string) => backendFetch('/api/admin/permission-matrix', { accessToken: token });

  let response = await attempt(accessToken);
  let refreshedTokens: any = null;

  if (response.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    if (refreshed?.tokens) {
      refreshedTokens = refreshed.tokens;
      response = await attempt(refreshed.tokens.access_token);
    }
  }

  const body = await readJsonBody(response);

  if (!response.ok) {
    const next = NextResponse.json(
      Object.keys(body).length > 0 ? body : { detail: 'admin.permission_matrix_failed' },
      { status: response.status || 500 },
    );
    if (response.status === 401) {
      clearAuthCookies(next);
    } else if (refreshedTokens) {
      setAuthCookies(next, refreshedTokens);
    }
    return next;
  }

  const next = NextResponse.json(normalizePermissionMatrix(body));
  if (refreshedTokens) {
    setAuthCookies(next, refreshedTokens);
  }
  return next;
}
