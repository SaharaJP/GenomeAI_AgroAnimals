import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const farmId = request.nextUrl.searchParams.get('farm_id') ?? 'demo-farm-v1';
  const { accessToken } = await getAuthTokens();

  const headers: Record<string, string> = {
    'content-type': 'application/json',
  };
  if (accessToken) {
    headers['authorization'] = `Bearer ${accessToken}`;
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(
      `${config.backendBaseUrl}/api/ai/insights/scan-now?farm_id=${encodeURIComponent(farmId)}`,
      { method: 'POST', headers },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  const text = await backendResponse.text().catch(() => '');
  return new NextResponse(text, {
    status: backendResponse.status,
    headers: { 'content-type': 'application/json' },
  });
}
