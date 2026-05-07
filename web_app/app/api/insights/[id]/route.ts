import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

async function proxy(request: NextRequest, id: string, method: 'GET' | 'PATCH' | 'DELETE') {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const body = method === 'PATCH' ? await request.text() : undefined;
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/insights/${encodeURIComponent(id)}`,
      { method, headers, body, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { 'content-type': 'application/json' },
  });
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return proxy(request, (await params).id, 'GET');
}
export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return proxy(request, (await params).id, 'PATCH');
}
export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return proxy(request, (await params).id, 'DELETE');
}
