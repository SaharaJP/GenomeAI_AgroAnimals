import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { getServerAppConfig } from '@/lib/config';

const config = getServerAppConfig();

export async function getAuthTokens() {
  const cookieStore = await cookies();
  return {
    accessToken: cookieStore.get(config.authCookieNames.accessToken)?.value,
    refreshToken: cookieStore.get(config.authCookieNames.refreshToken)?.value,
  };
}

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: false,
    path: '/',
    maxAge,
  };
}

export function clearAuthCookies(response: NextResponse) {
  response.cookies.set(config.authCookieNames.accessToken, '', {
    ...cookieOptions(0),
    expires: new Date(0),
  });
  response.cookies.set(config.authCookieNames.refreshToken, '', {
    ...cookieOptions(0),
    expires: new Date(0),
  });
}

export function setAuthCookies(
  response: NextResponse,
  tokens:
    | {
        access_token: string;
        refresh_token: string;
        expires_in_sec: number;
        refresh_expires_in_sec: number;
      }
    | {
        accessToken: string;
        refreshToken: string;
        expiresInSec: number;
        refreshExpiresInSec: number;
      },
) {
  const normalized =
    'access_token' in tokens
      ? {
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          expiresInSec: tokens.expires_in_sec,
          refreshExpiresInSec: tokens.refresh_expires_in_sec,
        }
      : tokens;

  response.cookies.set(
    config.authCookieNames.accessToken,
    normalized.accessToken,
    cookieOptions(normalized.expiresInSec),
  );
  response.cookies.set(
    config.authCookieNames.refreshToken,
    normalized.refreshToken,
    cookieOptions(normalized.refreshExpiresInSec),
  );
}

export async function backendFetch(
  path: string,
  init?: RequestInit & { accessToken?: string },
) {
  const headers = new Headers(init?.headers || {});
  if (init?.accessToken) {
    headers.set('authorization', `Bearer ${init.accessToken}`);
  }
  return fetch(`${config.backendBaseUrl}${path}`, {
    ...init,
    headers,
    cache: 'no-store',
  });
}

export async function refreshAccessToken(refreshToken: string) {
  const response = await backendFetch('/api/app/v1/auth/refresh', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      refresh_token: refreshToken,
      device: {
        platform: 'web_app',
        device_label: 'Next.js web shell',
      },
    }),
  });

  if (!response.ok) return null;

  return response.json() as Promise<{
    tokens: {
      access_token: string;
      refresh_token: string;
      expires_in_sec: number;
      refresh_expires_in_sec: number;
    };
  }>;
}
