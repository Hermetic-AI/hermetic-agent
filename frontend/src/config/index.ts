// Runtime configuration for the OpenAgent frontend.
//
// VITE_API_BASE_URL controls the prefix prepended to every API call.
// - In dev, leave it empty so requests go through the Vite proxy at `/api`
//   (see vite.config.ts).
// - In production, set it to the absolute backend URL.
//
// VITE_MCP_TOKEN is forwarded as the `X-MCP-Token` header to the agent
// bridge.  The flight query MCP expects it for tenant-isolated calls.
//
// VITE_CRM_TOKEN (build-time) or the value stored in localStorage under
// "crm_token" (runtime, set via the Settings panel) is forwarded as
// `X-CRM-Token` on every request.  This is the same token the user
// receives after logging into https://crmdev.feiheair.com via the
// `traveldev.feiheair.com/api/sys/logonV2` endpoint.

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
  /** Read the current CRM token (env wins, then localStorage). */
  getCrmToken: readCrmToken,
  /** Set / clear the runtime CRM token.  Pass empty string to clear. */
  setCrmToken: writeCrmToken,
  appName: 'OpenAgent',
  version: '0.1.0',
} as const;

export type Config = typeof config;
