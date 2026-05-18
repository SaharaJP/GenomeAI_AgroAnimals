import { apiFetch } from './client';

export type AuthUserSummary = {
  id: number;
  username: string;
  role: string | null;
};

type ListUsersResponse = {
  users: Array<{ id: number | string; username: string | null; role: string | null }>;
};

export async function listActiveUsers(limit: number = 500): Promise<AuthUserSummary[]> {
  const res = await apiFetch<ListUsersResponse>(`/api/users_v2?limit=${encodeURIComponent(limit)}`);
  return (res.users ?? []).map((u) => ({
    id: typeof u.id === 'number' ? u.id : Number(u.id),
    username: u.username ?? `user_${u.id}`,
    role: u.role ?? null,
  }));
}
