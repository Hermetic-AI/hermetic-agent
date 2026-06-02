// Tools service — wraps the /agent/tools endpoints.

import { http } from './http';
import type { Tool, ToolsResponse } from '../types';

const BASE = '/agent/tools';

export const toolsService = {
  list(signal?: AbortSignal) {
    return http.get<ToolsResponse>(BASE, { signal });
  },

  register(
    payload: {
      name: string;
      description?: string;
      input_schema?: Record<string, unknown>;
      handler?: unknown;
      remote_url?: string;
      remote_tool_name?: string;
      enabled?: boolean;
    },
    signal?: AbortSignal,
  ) {
    return http.post<{ success: true; tool: Tool }>(BASE, payload, { signal });
  },

  setEnabled(name: string, enabled: boolean, signal?: AbortSignal) {
    return http.patch<{ success: true; tool: Tool | null }>(
      `${BASE}/${encodeURIComponent(name)}/enabled`,
      { enabled },
      { signal },
    );
  },
};
