// useTools — fetches the current tools list, with toggle support.

import { useCallback, useEffect, useState } from 'react';
import { toolsService, ApiError } from '../services';
import type { Tool } from '../types';

export interface UseToolsResult {
  tools: Tool[];
  loading: boolean;
  error: string | null;
  setEnabled: (name: string, enabled: boolean) => Promise<void>;
  refresh: () => void;
}

export function useTools(): UseToolsResult {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    toolsService
      .list(ctrl.signal)
      .then((res) => {
        setTools(res.tools ?? []);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof ApiError) {
          setError(e.message);
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError('Failed to load tools');
        }
        setTools([]);
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  const setEnabled = useCallback(async (name: string, enabled: boolean) => {
    try {
      await toolsService.setEnabled(name, enabled);
      setTools((prev) =>
        prev.map((t) => (t.name === name ? { ...t, enabled } : t)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update tool');
      throw e;
    }
  }, []);

  return { tools, loading, error, setEnabled, refresh };
}
