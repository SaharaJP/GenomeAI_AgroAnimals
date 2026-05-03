import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function GET(request: NextRequest) {
  const farmId = request.nextUrl.searchParams.get('farm_id') ?? 'demo-farm-v1';
  const { accessToken } = await getAuthTokens();

  const headers: Record<string, string> = {
    accept: 'text/event-stream',
    'cache-control': 'no-cache',
  };
  if (accessToken) {
    headers['authorization'] = `Bearer ${accessToken}`;
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(
      `${config.backendBaseUrl}/api/ai/insights/events/stream?farm_id=${encodeURIComponent(farmId)}`,
      { headers },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  if (!backendResponse.ok || !backendResponse.body) {
    return NextResponse.json(
      { error: 'Backend error' },
      { status: backendResponse.status },
    );
  }

  return new NextResponse(backendResponse.body, {
    status: 200,
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      'x-accel-buffering': 'no',
      connection: 'keep-alive',
    },
  });
}
