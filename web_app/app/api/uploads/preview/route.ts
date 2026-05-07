import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = {};
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const ct = request.headers.get('content-type');
  if (ct) headers['content-type'] = ct;
  const url = new URL(request.url);
  const body = await request.arrayBuffer();
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/uploads/preview?${url.searchParams.toString()}`,
      { method: 'POST', headers, body },
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
