// Pool service — wraps the /agent/pool endpoints (Agent registration).

import { http } from './http';
import type { PoolStatsResponse } from '../types';

const BASE = '/agent/pool';

export const poolService = {
  stats(signal?: AbortSignal) {
    return http.get<PoolStatsResponse>(`${BASE}/stats`, { signal });
  },

  register(
    payload: {
      name: string;
      base_url: string;
      sdk_type: 'opencode' | 'claude_code';
      default_model?: string;
    },
    signal?: AbortSignal,
  ) {
    return http.post<{
      success: true;
      name: string;
      base_url: string;
      sdk_type: string;
      status: string;
    }>(`${BASE}/register`, payload, { signal });
  },

  unregister(name: string, signal?: AbortSignal) {
    return http.delete<{ success: boolean; name: string; error?: string }>(
      `${BASE}/${encodeURIComponent(name)}`,
      { signal },
    );
  },
};
