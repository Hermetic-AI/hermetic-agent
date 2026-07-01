import type { PromptAsset } from '../types/assets';

const BASE = '/agent/prompts';

export interface PromptListResult { total: number; items: PromptAsset[]; }

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

export const promptsApi = {
  list: (q: { limit?: number; offset?: number; code?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<PromptListResult>('GET', `${BASE}/?${p}`);
  },
  community: (q: { limit?: number; offset?: number; code?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<PromptListResult>('GET', `${BASE}/community?${p}`);
  },
  get: (code: string) => http<PromptAsset>('GET', `${BASE}/${code}`),
  create: (data: Omit<PromptAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility'>) =>
    http<PromptAsset>('POST', `${BASE}/`, data),
  update: (code: string, data: Partial<PromptAsset>) =>
    http<PromptAsset>('PUT', `${BASE}/${code}`, data),
  delete: (code: string) => http<{ success: boolean; code: string }>('DELETE', `${BASE}/${code}`),
  publish: (code: string, visibility: 'private' | 'public') =>
    http<PromptAsset>('POST', `${BASE}/${code}/publish`, { visibility }),
};