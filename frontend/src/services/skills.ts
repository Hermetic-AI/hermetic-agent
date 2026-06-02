// Skills service — wraps the /agent/skills endpoints.

import { http } from './http';
import type { Skill, SkillsResponse } from '../types';

const BASE = '/agent/skills';

export const skillsService = {
  list(signal?: AbortSignal) {
    return http.get<SkillsResponse>(BASE, { signal });
  },

  register(payload: Partial<Skill> & { name: string }, signal?: AbortSignal) {
    return http.post<{ success: true; skill: Skill }>(BASE, payload, { signal });
  },
};
