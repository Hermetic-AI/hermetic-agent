// useAdminModel — state machine for the "Models" Settings tab.
//
// Responsibilities:
//   1. 选定 opencode 节点 (agent name) — 默认用 readiness.agents[0]
//   2. 拉当前 policy / env / status
//   3. 本地草稿: model + env keys (允许增删 KEY)
//   4. save   = POST /policy + POST /env, 写到 runtime overlay
//   5. apply  = POST /policy/reload, supervisor SIGTERMs opencode, ~1s
//
// 设计原则: save 不重启 (用户可攒多次改动), apply 才重启 (破坏性).

import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminService } from '../services';
import type { OpencodeEnv, OpencodePolicy, OpencodeStatus } from '../services';
import { ApiError } from '../services';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';

export interface AdminModelState {
  /** 当前选中的 opencode 节点 name (默认 = agents[0]). */
  agentName: string;
  setAgentName: (name: string) => void;
  /** 已知的所有 opencode 节点 (从 useHealth 透传). */
  availableAgents: string[];
  setAvailableAgents: (names: string[]) => void;

  loadState: LoadState;
  error: string | null;

  /** 从服务器读到的当前生效 policy (baked ⨁ overlay). */
  policy: OpencodePolicy | null;
  /** 从服务器读到的当前 env.runtime (secret 遮蔽). */
  env: OpencodeEnv | null;
  /** opencode 进程状态 (pid / alive / active_model). */
  status: OpencodeStatus | null;

  /** 草稿: 用户编辑的 model 字符串. */
  modelDraft: string;
  setModelDraft: (m: string) => void;
  /** 草稿: 用户编辑的 env 字典 (key → value; null = 待删除). */
  envDraft: Record<string, string | null>;
  setEnvDraft: (next: Record<string, string | null>) => void;

  /** 把所有草稿写入 runtime overlay (model + env). 不重启. */
  save: () => Promise<void>;
  /** 触发 reload (SIGTERM opencode). 需先 save. */
  apply: () => Promise<void>;
  /** save + apply 一次性执行. */
  saveAndApply: () => Promise<void>;

  saving: boolean;
  applying: boolean;
  /** 最近一次 save/apply 的人类可读结果 ("ok pid=12→pid=58" 等). */
  lastResult: string | null;

  refresh: () => Promise<void>;
}

export function useAdminModel(): AdminModelState {
  const [agentName, setAgentNameState] = useState<string>('');
  const [availableAgents, setAvailableAgents] = useState<string[]>([]);

  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [error, setError] = useState<string | null>(null);

  const [policy, setPolicy] = useState<OpencodePolicy | null>(null);
  const [env, setEnv] = useState<OpencodeEnv | null>(null);
  const [status, setStatus] = useState<OpencodeStatus | null>(null);

  const [modelDraft, setModelDraft] = useState<string>('');
  const [envDraft, setEnvDraft] = useState<Record<string, string | null>>({});

  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!agentName) {
      setLoadState('idle');
      return;
    }
    setLoadState('loading');
    setError(null);
    try {
      const [pol, envRes, stat] = await Promise.all([
        adminService.getPolicy(agentName),
        adminService.getEnv(agentName),
        adminService.getStatus(agentName),
      ]);
      setPolicy(pol);
      setEnv(envRes);
      setStatus(stat);
      // 初始化草稿 (agent 切换或 refresh 时重置)
      const m =
        (pol.effective?.agent as { model?: string } | undefined)?.model ??
        (pol.runtime_overlay?.agent as { model?: string } | undefined)?.model ??
        '';
      setModelDraft(m);
      // env: 用运行时 overlay 的当前真实值 (但 secret 已经遮蔽, 用 *** 占位)
      setEnvDraft({ ...envRes.env });
      setLoadState('ready');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setLoadState('error');
    }
  }, [agentName]);

  useEffect(() => {
    if (agentName) {
      void refresh();
    }
  }, [agentName, refresh]);

  // 默认 agent: 拿 availableAgents 第一个
  useEffect(() => {
    if (!agentName && availableAgents.length > 0) {
      setAgentNameState(availableAgents[0]);
    }
  }, [agentName, availableAgents]);

  const setAgentName = useCallback((name: string) => {
    setAgentNameState(name);
    setLastResult(null);
  }, []);

  const save = useCallback(async () => {
    if (!agentName) return;
    setSaving(true);
    setError(null);
    try {
      // 1. policy (model)
      const trimmedModel = modelDraft.trim();
      const prevModel =
        (policy?.effective?.agent as { model?: string } | undefined)?.model ?? '';
      if (trimmedModel && trimmedModel !== prevModel) {
        await adminService.updatePolicy(agentName, {
          agent: { model: trimmedModel },
        });
      }
      // 2. env — 只送非空 / 非遮蔽值
      const envPayload: Record<string, string | null> = {};
      for (const [k, v] of Object.entries(envDraft)) {
        // *** 是后端遮蔽过的占位符, 没改 → 跳过
        if (v === '***' || v == null) continue;
        envPayload[k] = v;
      }
      if (Object.keys(envPayload).length > 0) {
        await adminService.updateEnv(agentName, envPayload);
      }
      setLastResult('已写入 runtime overlay (未重启). 点 "应用" 让 opencode 重新加载.');
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      throw e;
    } finally {
      setSaving(false);
    }
  }, [agentName, modelDraft, envDraft, policy, refresh]);

  const apply = useCallback(async () => {
    if (!agentName) return;
    setApplying(true);
    setError(null);
    try {
      const r = await adminService.reload(agentName);
      setLastResult(`${r.restart}. ${r.next}`);
      // 等待 supervisor 重启 (~1s), 然后拉新 status
      await new Promise((res) => setTimeout(res, 1500));
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      throw e;
    } finally {
      setApplying(false);
    }
  }, [agentName, refresh]);

  const saveAndApply = useCallback(async () => {
    await save();
    await apply();
  }, [save, apply]);

  return useMemo(
    () => ({
      agentName,
      setAgentName,
      availableAgents,
      setAvailableAgents,
      loadState,
      error,
      policy,
      env,
      status,
      modelDraft,
      setModelDraft,
      envDraft,
      setEnvDraft,
      save,
      apply,
      saveAndApply,
      saving,
      applying,
      lastResult,
      refresh,
    }),
    [
      agentName,
      setAgentName,
      availableAgents,
      loadState,
      error,
      policy,
      env,
      status,
      modelDraft,
      envDraft,
      save,
      apply,
      saveAndApply,
      saving,
      applying,
      lastResult,
      refresh,
    ],
  );
}
