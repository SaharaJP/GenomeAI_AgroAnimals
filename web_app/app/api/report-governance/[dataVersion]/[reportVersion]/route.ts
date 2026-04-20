import { NextRequest, NextResponse } from 'next/server';
import { backendFetch, clearAuthCookies, getAuthTokens, refreshAccessToken, setAuthCookies } from '@/lib/server/backend';

type RouteContext = { params: Promise<{ dataVersion: string; reportVersion: string }> };

async function forwardWithRefresh(path: string, request: NextRequest) {
  const { accessToken, refreshToken } = await getAuthTokens();
  const bodyText = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.text();
  const forward = async (token?: string) =>
    backendFetch(path, {
      method: request.method,
      accessToken: token,
      headers: { 'content-type': request.headers.get('content-type') || 'application/json' },
      body: bodyText,
    });
  let response = await forward(accessToken);
  if (response.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    if (refreshed?.tokens) {
      response = await forward(refreshed.tokens.access_token);
      const body = await response.text();
      const next = new NextResponse(body, { status: response.status, headers: { 'content-type': response.headers.get('content-type') || 'application/json' } });
      if (response.ok) setAuthCookies(next, refreshed.tokens);
      else clearAuthCookies(next);
      return next;
    }
  }
  const body = await response.text();
  const next = new NextResponse(body, { status: response.status, headers: { 'content-type': response.headers.get('content-type') || 'application/json' } });
  if (response.status === 401) clearAuthCookies(next);
  return next;
}

export async function GET(_request: NextRequest, context: RouteContext) {
  const { dataVersion, reportVersion } = await context.params;
  const path = `/api/reports_v1/approval?data_version=${encodeURIComponent(dataVersion)}&report_version=${encodeURIComponent(reportVersion)}`;
  return forwardWithRefresh(path, _request);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { dataVersion, reportVersion } = await context.params;
  const body = await request.json().catch(() => ({}));
  const action = String(body?.action || '').trim();
  if (!['approve', 'reject', 'archive'].includes(action)) {
    return NextResponse.json({ detail: 'Unsupported report governance action' }, { status: 400 });
  }
  const payload = JSON.stringify({ data_version: dataVersion, comment: body?.comment || null });
  const syntheticRequest = new NextRequest(request.url, { method: 'POST', headers: request.headers, body: payload });
  const path = `/api/reports_v1/${encodeURIComponent(reportVersion)}/${action}`;
  return forwardWithRefresh(path, syntheticRequest);
}
