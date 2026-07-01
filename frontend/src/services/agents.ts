import type { AgentAsset } from '../types/assets';

const BASE = '/agent/agents';

export interface AgentListResult { total: number; items: AgentAsset[]; }

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

export const agentsApi = {
  list: (q: { limit?: number; offset?: number; code?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<AgentListResult>('GET', `${BASE}/?${p}`);
  },
  community: (q: { limit?: number; offset?: number; code?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<AgentListResult>('GET', `${BASE}/community?${p}`);
  },
  get: (code: string) => http<AgentAsset>('GET', `${BASE}/${code}`),
  create: (data: Omit<AgentAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility'>) =>
    http<AgentAsset>('POST', `${BASE}/`, data),
  update: (code: string, data: Partial<AgentAsset>) =>
    http<AgentAsset>('PUT', `${BASE}/${code}`, data),
  delete: (code: string) => http<{ success: boolean; code: string }>('DELETE', `${BASE}/${code}`),
  publish: (code: string, visibility: 'private' | 'public') =>
    http<AgentAsset>('POST', `${BASE}/${code}/publish`, { visibility }),
};