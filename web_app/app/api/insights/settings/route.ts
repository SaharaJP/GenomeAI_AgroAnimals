import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

async function proxy(request: NextRequest, method: 'GET' | 'PUT') {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const url = new URL(request.url);
  const body = method === 'PUT' ? await request.text() : undefined;
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/insights/settings?${url.searchParams.toString()}`,
      { method, headers, body, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const text = await r.text();
  return new NextResponse(text, { status: r.status, headers: { 'content-type': 'application/json' } });
}

export async function GET(request: NextRequest) { return proxy(request, 'GET'); }
export async function PUT(request: NextRequest) { return proxy(request, 'PUT'); }
