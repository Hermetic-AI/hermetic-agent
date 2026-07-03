// useMcpConfigs — fetches the list of MCP config assets from `/agent/mcp-configs/`.
//
// Mirrors useAgents (tick-refetch, no abort, alive guard).  Used by the
// chat shell to populate the MCP asset picker.  Talks through the Vite
// dev-server proxy via `mcpConfigsApi.list()`.

import { useEffect, useState } from 'react';
import { mcpConfigsApi } from '../services/mcp_configs';
import type { McpConfigAsset } from '../types/assets';

export interface UseMcpConfigsResult {
  mcps: McpConfigAsset[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useMcpConfigs(): UseMcpConfigsResult {
  const [mcps, setMcps] = useState<McpConfigAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    mcpConfigsApi
      .list({ limit: 100 })
      .then((res) => {
        if (!alive) return;
        setMcps(res.items ?? []);
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Failed to load MCP configs');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  return { mcps, loading, error, refresh: () => setTick((t) => t + 1) };
}
