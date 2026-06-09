// Scenario service — wraps `/agent/scenarios` for the selector / debug UI.

import { http } from './http';
import type { ScenarioSummary, ScenariosListResponse } from '../types';

const SCENARIO_BASE = '/agent/scenarios';
const SCENARIO_LIST_PATH = '/agent/scenarios/';

export const scenarioService = {
  /** List all registered scenarios. */
  list(signal?: AbortSignal) {
    return http.get<ScenariosListResponse>(SCENARIO_LIST_PATH, {
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
