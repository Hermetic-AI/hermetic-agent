// Runtime configuration for the OpenAgent frontend.
//
// VITE_API_BASE_URL controls the prefix prepended to every API call.
// - In dev, leave it empty so requests go through the Vite proxy at `/api`
//   (see vite.config.ts).
// - In production, set it to the absolute backend URL.
const rawBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim();

export const config = {
  apiBaseUrl: rawBase ? rawBase.replace(/\/+$/, '') : '/api',
  appName: 'OpenAgent',
  version: '0.1.0',
} as const;

export type Config = typeof config;
