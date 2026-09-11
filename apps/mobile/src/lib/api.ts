// The one door to our backend. Every call carries the Supabase access token
// (refreshed automatically by supabase-js) and the device time zone, which the
// API uses to default the user's profile.
import { config } from '@/lib/config';
import { supabase } from '@/lib/supabase';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function errorText(res: Response): Promise<string> {
  // FastAPI puts the reason in {"detail": ...}; fall back to raw text.
  try {
    const body = await res.json();
    return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body);
  } catch {
    return res.statusText;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('X-Timezone', Intl.DateTimeFormat().resolvedOptions().timeZone);
  if (session) headers.set('Authorization', `Bearer ${session.access_token}`);
  if (init.body) headers.set('Content-Type', 'application/json');

  const res = await fetch(`${config.apiUrl}${path}`, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, await errorText(res));
  if (res.status === 204) return undefined as T; // no content (deletes)
  return res.json() as Promise<T>;
}
