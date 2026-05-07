import { NextRequest, NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function POST(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { accessToken } = await getAuthTokens();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;
  let r: Response;
  try {
    r = await fetch(
      `${config.backendBaseUrl}/api/app/v1/qc/incidents/${encodeURIComponent(id)}/dismiss`,
      { method: 'POST', headers },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }
  const text = await r.text();
  return new NextResponse(text, { status: r.status, headers: { 'content-type': 'application/json' } });
}
