// Scenario service — wraps `/agent/scenarios` for the selector / debug UI.

import { http } from './http';
import type { ScenarioSummary, ScenariosListResponse } from '../types';

const SCENARIO_BASE = '/agent/scenarios';

export const scenarioService = {
  /** List all registered scenarios, optionally filtered by tag. */
  list(tag?: string, signal?: AbortSignal) {
    return http.get<ScenariosListResponse>(SCENARIO_BASE, {
      query: tag ? { tag } : undefined,
      signal,
    });
  },

  /** Fetch a single scenario by name. */
  get(name: string, signal?: AbortSignal) {
    return http.get<{ success: boolean; scenario: Record<string, unknown> }>(
      `${SCENARIO_BASE}/${encodeURIComponent(name)}`,
      { signal },
    );
  },
};

export type { ScenarioSummary };
