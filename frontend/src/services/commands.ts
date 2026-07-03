import type { CommandAsset } from '../types/assets';

const BASE = '/agent/commands';

export interface CommandListResult { total: number; items: CommandAsset[]; }

async function http<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(`${r.status} ${r.statusText}: ${err.error ?? ''}`);
  }
  return r.json() as Promise<T>;
}

export const commandsApi = {
  list: (q: { limit?: number; offset?: number; code?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<CommandListResult>('GET', `${BASE}/?${p}`);
  },
  community: (q: { limit?: number; offset?: number; code?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<CommandListResult>('GET', `${BASE}/community?${p}`);
  },
  get: (code: string) => http<CommandAsset>('GET', `${BASE}/${code}`),
  getBySlash: (slashCommand: string) =>
    http<CommandAsset>('GET', `${BASE}/by-slash/${encodeURIComponent(slashCommand)}`),
  create: (data: Omit<CommandAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility'>) =>
    http<CommandAsset>('POST', `${BASE}/`, data),
  update: (code: string, data: Partial<CommandAsset>) =>
    http<CommandAsset>('PUT', `${BASE}/${code}`, data),
  delete: (code: string) => http<{ success: boolean; code: string }>('DELETE', `${BASE}/${code}`),
  publish: (code: string, visibility: 'private' | 'public') =>
    http<CommandAsset>('POST', `${BASE}/${code}/publish`, { visibility }),
};