import { NextResponse } from 'next/server';

type Settings = {
  notifications: { kpiInsightsEmail: boolean };
  weeklyBriefing: boolean;
};

const defaults: Settings = {
  notifications: { kpiInsightsEmail: true },
  weeklyBriefing: true,
};

// Module-level store for demo (resets on server restart)
let store: Settings = { ...defaults };

export async function GET() {
  return NextResponse.json(store);
}

export async function POST(req: Request) {
  const body = await req.json() as Partial<Settings>;
  store = { ...store, ...body };
  return NextResponse.json(store);
}
