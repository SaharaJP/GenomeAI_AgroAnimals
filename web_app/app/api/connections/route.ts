import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    farms: [{ id: 'demo-farm', name: 'Демо-ферма', status: 'Sandbox' }],
  });
}
