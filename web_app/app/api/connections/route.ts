import { NextResponse } from 'next/server';
import { getAuthTokens } from '@/lib/server/backend';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function GET() {
  try {
    const { accessToken } = await getAuthTokens();
    const headers: Record<string, string> = {};
    if (accessToken) headers['authorization'] = `Bearer ${accessToken}`;

    const res = await fetch(`${config.backendBaseUrl}/api/app/v1/auth/me`, { headers });
    if (!res.ok) return NextResponse.json({ farms: [] });

    const me = await res.json();
    const farmIds: string[] = me?.scope?.allowed_farm_ids ?? [];
    const demoMode: boolean = me?.demo_mode ?? false;

    const farms = farmIds.map((id: string) => ({
      id,
      name: id,
      status: demoMode ? 'Sandbox' : 'Active',
    }));

    return NextResponse.json({ farms });
  } catch {
    return NextResponse.json({ farms: [] });
  }
}
