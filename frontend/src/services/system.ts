// System service — health/readiness checks.

import { http } from './http';
import type { HealthResponse, ReadyResponse } from '../types';

export const systemService = {
  health(signal?: AbortSignal) {
    return http.get<HealthResponse>('/health', { signal });
  },

  ready(signal?: AbortSignal) {
    return http.get<ReadyResponse>('/ready', { signal });
  },
};
