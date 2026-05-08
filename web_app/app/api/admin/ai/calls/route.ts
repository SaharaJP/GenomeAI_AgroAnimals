import { NextResponse } from 'next/server';
import { backendFetch, clearAuthCookies, getAuthTokens, refreshAccessToken, setAuthCookies } from '@/lib/server/backend';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const path = `/api/admin/ai/calls${qs ? `?${qs}` : ''}`;

  const { accessToken, refreshToken } = await getAuthTokens();
  const attempt = (token?: string) => backendFetch(path, { accessToken: token });

  let response = await attempt(accessToken);
  let refreshedTokens: { access_token: string; refresh_token: string; expires_in_sec: number; refresh_expires_in_sec: number } | null = null;

  if (response.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    if (refreshed?.tokens) {
      refreshedTokens = refreshed.tokens;
      response = await attempt(refreshed.tokens.access_token);
    }
  }

  const text = await response.text();
  const next = new NextResponse(text, {
    status: response.status,
    headers: { 'content-type': response.headers.get('content-type') || 'application/json' },
  });
  if (response.status === 401) clearAuthCookies(next);
  else if (refreshedTokens) setAuthCookies(next, refreshedTokens);
  return next;
}
