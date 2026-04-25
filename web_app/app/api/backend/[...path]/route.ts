import { NextRequest, NextResponse } from 'next/server';
import {
  backendFetch,
  clearAuthCookies,
  getAuthTokens,
  refreshAccessToken,
  setAuthCookies,
} from '@/lib/server/backend';

type RouteContext = { params: Promise<{ path: string[] }> };

function isBinaryContentType(ct: string): boolean {
  return (
    ct.startsWith('application/pdf') ||
    ct.startsWith('image/') ||
    ct.startsWith('video/') ||
    ct.startsWith('audio/') ||
    ct.startsWith('application/octet-stream') ||
    ct.startsWith('application/zip')
  );
}

async function buildNextResponse(
  response: Response,
  extra?: (nr: NextResponse) => void,
): Promise<NextResponse> {
  const contentType = response.headers.get('content-type') || 'application/json';
  const contentDisposition = response.headers.get('content-disposition');

  let nr: NextResponse;
  if (isBinaryContentType(contentType)) {
    const buf = await response.arrayBuffer();
    nr = new NextResponse(buf, { status: response.status, headers: { 'content-type': contentType } });
  } else {
    const body = await response.text();
    nr = new NextResponse(body, { status: response.status, headers: { 'content-type': contentType } });
  }
  if (contentDisposition) nr.headers.set('content-disposition', contentDisposition);
  extra?.(nr);
  return nr;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const search = request.nextUrl.search || '';
  const backendPath =
    path[0] === 'api'
      ? `/${path.join('/')}${search}`
      : `/api/app/v1/${path.join('/')}${search}`;

  const { accessToken, refreshToken } = await getAuthTokens();
  const bodyText = ['GET', 'HEAD'].includes(request.method)
    ? undefined
    : await request.text();

  const forward = async (token?: string) =>
    backendFetch(backendPath, {
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
      return buildNextResponse(response, (nr) => {
        if (response.ok) setAuthCookies(nr, refreshed.tokens);
        else clearAuthCookies(nr);
      });
    }
  }

  return buildNextResponse(response, (nr) => {
    if (response.status === 401) clearAuthCookies(nr);
  });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
