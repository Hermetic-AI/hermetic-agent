import type { SkillAsset } from '../types/assets';

const BASE = '/agent/skills-db';

export interface SkillListResult { total: number; skills: SkillAsset[]; }

export interface CreateSkillInput {
  code: string;
  name: string;
  version?: number;
  status?: 'enabled' | 'disabled' | 'draft';
  description?: string | null;
  triggers?: string[] | null;
  prompt_template?: string | null;
  mcp_tools?: unknown;
}

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

export const skillsApi = {
  list: (q: { limit?: number; offset?: number; code?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<SkillListResult>('GET', `${BASE}/?${p}`);
  },
  get: (code: string) => http<SkillAsset>('GET', `${BASE}/${encodeURIComponent(code)}`),
  create: (data: CreateSkillInput) =>
    http<SkillAsset>('POST', `${BASE}/`, data),
  update: (code: string, data: Partial<CreateSkillInput>) =>
    http<SkillAsset>('PUT', `${BASE}/${encodeURIComponent(code)}`, data),
  delete: (code: string) =>
    http<{ success: boolean; code: string }>('DELETE', `${BASE}/${encodeURIComponent(code)}`),
};
