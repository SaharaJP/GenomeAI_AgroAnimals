import { NextResponse } from 'next/server';
import { backendFetch, clearAuthCookies, getAuthTokens, refreshAccessToken, setAuthCookies } from '@/lib/server/backend';

export async function GET() {
  const { accessToken, refreshToken } = await getAuthTokens();
  const attempt = (token?: string) => backendFetch('/api/observability', { accessToken: token });
  let response = await attempt(accessToken);
  if (response.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    if (refreshed?.tokens) {
      response = await attempt(refreshed.tokens.access_token);
      const body = await response.json().catch(() => null);
      if (response.ok && body) {
        const next = NextResponse.json(body);
        setAuthCookies(next, refreshed.tokens);
        return next;
      }
    }
  }
  const body = await response.json().catch(() => ({ detail: 'observability.failed' }));
  const next = NextResponse.json(body, { status: response.status });
  if (response.status === 401) clearAuthCookies(next);
  return next;
}
