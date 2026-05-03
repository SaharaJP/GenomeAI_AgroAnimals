import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(request: NextRequest) {
  const body = await request.text();
  const { accessToken } = await getAuthTokens();

  const headers: Record<string, string> = {
    'content-type': 'application/json',
    accept: 'text/event-stream',
  };
  if (accessToken) {
    headers['authorization'] = `Bearer ${accessToken}`;
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${config.backendBaseUrl}/api/ai/ask-farm`, {
      method: 'POST',
      headers,
      body,
      // @ts-expect-error — Node fetch duplex required for streaming body
      duplex: 'half',
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  if (!backendResponse.ok || !backendResponse.body) {
    const text = await backendResponse.text().catch(() => '');
    return NextResponse.json(
      { error: text || 'Backend error' },
      { status: backendResponse.status },
    );
  }

  // Stream the SSE response directly back to the client
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
