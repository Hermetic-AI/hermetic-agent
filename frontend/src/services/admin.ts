// Admin service — wraps the opencode-sandbox admin API proxies on the Hub.
//
// All endpoints are mounted under /agent/admin/opencode/<name>/... and proxy
// to the opencode container's admin_server (:7778) which in turn mutates
// /tmp/opencode-sandbox/{env.runtime, policy.runtime.json} and signals
// the supervisor to restart opencode.
//
// The frontend treats these as 3 logical operations:
//   1. read  — current state (model / env / pid / alive)
//   2. write — queue changes (model + env, partial updates, no effect yet)
//   3. apply — POST /policy/reload, supervisor SIGTERMs opencode, ~1s
//
// We do NOT auto-apply on every change so the user can batch model + env +
// custom vars and apply in one shot (opencode restart is disruptive).

import { http } from './http';

const BASE = '/agent/admin/opencode';

export interface OpencodePolicy {
  baked: Record<string, unknown>;
  runtime_overlay: Record<string, unknown>;
  effective: Record<string, unknown>;
}

export interface OpencodeEnv {
  runtime_path: string;
  exists: boolean;
  env: Record<string, string>;
  next?: string;
}

export interface OpencodeStatus {
  opencode_alive: boolean;
  opencode_pid: number | null;
  active_model: string | null;
}

export interface ReloadResult {
  ok: boolean;
  render: string;
  restart: string;
  next: string;
}

export const adminService = {
  /** 当前生效的 policy (baked ⨁ runtime overlay). */
  getPolicy(name: string, signal?: AbortSignal) {
    return http.get<OpencodePolicy>(
      `${BASE}/${encodeURIComponent(name)}/policy`,
      { signal },
    );
  },

  /**
   * Partial update on policy runtime overlay (deep-merged with baked).
   * 例: ``{ "agent": { "model": "openai/qwen3.6-flash" } }``
   * 例: ``{ "tool_level": "standard" }``
   * 字段值传 ``null`` = 从 overlay 里删 (回落 baked).
   */
  updatePolicy(
    name: string,
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ) {
    return http.post<{ ok: boolean; effective: Record<string, unknown>; next: string }>(
      `${BASE}/${encodeURIComponent(name)}/policy`,
      body,
      { signal },
    );
  },

  /**
   * 触发 supervisor 重启 opencode (重渲 config.json + SIGTERM).
   * 这是唯一会真正让 opencode 重新读 env + config 的端点.
   */
  reload(name: string, signal?: AbortSignal) {
    return http.post<ReloadResult>(
      `${BASE}/${encodeURIComponent(name)}/policy/reload`,
      undefined,
      { signal },
    );
  },

  /** 当前 env.runtime (secret 值遮蔽为 "***"). */
  getEnv(name: string, signal?: AbortSignal) {
    return http.get<OpencodeEnv>(
      `${BASE}/${encodeURIComponent(name)}/env`,
      { signal },
    );
  },

  /**
   * Partial update on env.runtime. 例:
   *   ``{ "OPENAI_API_KEY": "sk-...", "OPENAI_BASE_URL": "https://..." }``
   * 字段值传 ``null`` = 删该 KEY. 写入 chmod 600.
   */
  updateEnv(
    name: string,
    body: Record<string, string | null>,
    signal?: AbortSignal,
  ) {
    return http.post<{ ok: boolean; wrote: number; next: string }>(
      `${BASE}/${encodeURIComponent(name)}/env`,
      body,
      { signal },
    );
  },

  /** 进程状态 (pid + alive + 渲染后的 active_model). */
  getStatus(name: string, signal?: AbortSignal) {
    return http.get<OpencodeStatus>(
      `${BASE}/${encodeURIComponent(name)}/opencode`,
      { signal },
    );
  },
};
