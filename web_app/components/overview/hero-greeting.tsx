'use client';

import { useAuth } from '@/components/auth/auth-provider';
import type { AuthMeResponse } from '@/lib/api/contracts';

function getGreetingWord(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Доброе утро';
  if (hour < 18) return 'Добрый день';
  return 'Добрый вечер';
}

type AuthCtx = { me: AuthMeResponse | null; loading: boolean };

export function HeroGreeting() {
  const auth = useAuth() as AuthCtx;
  const name = auth.loading ? '…' : (auth.me?.user.username ?? 'Пользователь');

  return (
    <h1 className="overview-greeting">
      {getGreetingWord()}, {name}!
    </h1>
  );
}
