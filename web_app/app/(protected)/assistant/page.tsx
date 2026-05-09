import { redirect } from 'next/navigation';

export default async function AssistantPageRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      for (const v of value) usp.append(key, String(v));
    } else if (value !== undefined) {
      usp.set(key, String(value));
    }
  }
  const qs = usp.toString();
  redirect(`/copilot${qs ? `?${qs}` : ''}`);
}
