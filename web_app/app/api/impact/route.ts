import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const body = await request.text();
  const { accessToken } = await getAuthTokens();

  const headers: Record<string, string> = {
    'content-type': 'application/json',
  };
  if (accessToken) {
    headers['authorization'] = `Bearer ${accessToken}`;
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${config.backendBaseUrl}/api/impact`, {
      method: 'POST',
      headers,
      body,
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  const text = await backendResponse.text().catch(() => '');
  return new NextResponse(text, {
    status: backendResponse.status,
    headers: { 'content-type': 'application/json' },
  });
}
