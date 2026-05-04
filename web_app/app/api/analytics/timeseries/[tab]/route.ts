import { NextRequest, NextResponse } from 'next/server';
import { backendFetch, getAuthTokens } from '@/lib/server/backend';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ tab: string }> },
) {
  const { tab } = await params;
  const { searchParams } = request.nextUrl;
  const weeks = searchParams.get('weeks') ?? '26';
  const farmId = searchParams.get('farm_id');

  const { accessToken } = await getAuthTokens();

  const qs = new URLSearchParams({ weeks });
  if (farmId) qs.set('farm_id', farmId);

  let res: Response;
  try {
    res = await backendFetch(`/api/analytics/timeseries/${tab}?${qs}`, {
      accessToken: accessToken ?? undefined,
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  const text = await res.text().catch(() => '');
  return new NextResponse(text, {
    status: res.status,
    headers: { 'content-type': 'application/json' },
  });
}
