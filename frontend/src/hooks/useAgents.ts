// useAgents — fetches the list of agent assets from `/agent/agents/`.
//
// Used by the chat toolbar to populate the agent picker dropdown.  The user
// selects one and `ChatPage` passes its `code` to `useChatStream` as
// `agentCode`, which the hub resolves and injects into the LLM call.

import { useEffect, useState } from 'react';
import { agentsApi } from '../services/agents';
import type { AgentAsset } from '../types/assets';

export interface UseAgentsResult {
  agents: AgentAsset[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useAgents(): UseAgentsResult {
  const [agents, setAgents] = useState<AgentAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    agentsApi
      .list({ limit: 100 })
      .then((res) => {
        if (!alive) return;
        setAgents(res.items ?? []);
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Failed to load agents');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  return { agents, loading, error, refresh: () => setTick((t) => t + 1) };
}
