import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function GET(request: NextRequest) {
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = {};
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  const url = new URL(request.url);
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/uploads/template?${url.searchParams.toString()}`,
      { headers, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const buf = await r.arrayBuffer();
  return new NextResponse(buf, {
    status: r.status,
    headers: {
      'content-type': r.headers.get('content-type') ?? 'application/octet-stream',
      'content-disposition': r.headers.get('content-disposition') ?? '',
    },
  });
}
