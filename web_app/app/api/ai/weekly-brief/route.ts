import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const body = await request.text();
  const { accessToken } = await getAuthTokens();

  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${config.backendBaseUrl}/api/ai/weekly-brief`, {
      method: 'POST',
      headers,
      body,
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  if (!backendResponse.ok) {
    const text = await backendResponse.text().catch(() => '');
    return NextResponse.json({ error: text || 'Backend error' }, { status: backendResponse.status });
  }

  const data = await backendResponse.json();
  return NextResponse.json(data);
}
