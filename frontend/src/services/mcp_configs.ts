import type { McpConfigAsset, McpType } from '../types/assets';

const BASE = '/agent/mcp-configs';

export interface McpConfigListResult { total: number; items: McpConfigAsset[]; }

export interface CreateMcpConfigInput {
  code: string;
  name: string;
  mcp_type?: McpType;
  status?: 'enabled' | 'disabled' | 'draft';
  url?: string | null;
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;
  cwd?: string | null;
  headers?: Record<string, string> | null;
  allowed_tools?: string[] | null;
  disabled?: boolean;
  config?: Record<string, unknown> | null;
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

export const mcpConfigsApi = {
  list: (q: { limit?: number; offset?: number; code?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<McpConfigListResult>('GET', `${BASE}/?${p}`);
  },
  get: (code: string) => http<McpConfigAsset>('GET', `${BASE}/${encodeURIComponent(code)}`),
  create: (data: CreateMcpConfigInput) =>
    http<McpConfigAsset>('POST', `${BASE}/`, data),
  update: (code: string, data: Partial<CreateMcpConfigInput>) =>
    http<McpConfigAsset>('PUT', `${BASE}/${encodeURIComponent(code)}`, data),
  delete: (code: string) =>
    http<{ success: boolean; code: string }>('DELETE', `${BASE}/${encodeURIComponent(code)}`),
};
