// Runtime configuration for the hermetic-agent frontend.
//
// VITE_API_BASE_URL controls the prefix prepended to every API call.
// - In dev, leave it empty so requests go through the Vite proxy at `/api`
//   (see vite.config.ts).
// - In production, set it to the absolute backend URL.
//
// VITE_MCP_TOKEN is forwarded as the `X-MCP-Token` header to the agent
// bridge.  Business SKILLs use it for tenant-isolated MCP calls.

const STORAGE_KEY_CRM_TOKEN = 'crm_token';

const rawBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim();
const rawMcpToken = (import.meta.env.VITE_MCP_TOKEN ?? '').trim();
const rawCrmToken = (import.meta.env.VITE_CRM_TOKEN ?? '').trim();

function readCrmToken(): string {
  if (rawCrmToken) return rawCrmToken;
  try {
    return window.localStorage.getItem(STORAGE_KEY_CRM_TOKEN) ?? '';
  } catch {
    return '';
  }
}

function writeCrmToken(token: string): void {
  try {
    if (token) window.localStorage.setItem(STORAGE_KEY_CRM_TOKEN, token);
    else window.localStorage.removeItem(STORAGE_KEY_CRM_TOKEN);
  } catch {
    // ignore quota / privacy errors
  }
}

export const config = {
  apiBaseUrl: rawBase ? rawBase.replace(/\/+$/, '') : '/api',
  mcpToken: rawMcpToken,
  getCrmToken: readCrmToken,
  setCrmToken: writeCrmToken,
  appName: 'hermetic-agent',
  version: '0.1.0',
} as const;

export type Config = typeof config;
