import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChatMessage } from '../../types';
import {
  useChatStream,
  useChatSession,
  useHealth,
  useAgents,
  usePrompts,
  useCommands,
  useSkills,
  useMcpConfigs,
} from '../../hooks';
import { MessageList, ChatInput, ChatBubble, WelcomeMessage } from '../chat';
import type { AssetUseRequest } from '../../lib';
import {
  useActiveAssets,
  emit,
  ASSET_INVOKE_EVENT,
  COMMAND_EXECUTED_EVENT,
  ACCESS_LEVEL_CHANGED_EVENT,
  CRAFT_AGENT_REQUESTED_EVENT,
} from '../../lib';
import type { AssetInvokeRequest, AccessLevel, CommandExecutedEvent } from '../../lib';
import type {
  PromptAsset,
  CommandAsset,
  SkillAsset,
  McpConfigAsset,
  AgentAsset,
} from '../../types/assets';
import { promptsApi } from '../../services/prompts';
import { commandsApi } from '../../services/commands';
import { skillsApi } from '../../services/skills';
import { mcpConfigsApi } from '../../services/mcp_configs';
import { logger } from '../../utils/logger';
import './ChatPage.css';
import './chat-shell.css';

interface ChatPageProps {
  onQuickReply?: (message: string) => void;
  /** Pending prompt injected from another page. */
  pendingPrompt?: string | null;
  /** Cleared once the prompt has been consumed. */
  onPendingPromptConsumed?: () => void;
  /**
   * "Use this asset in chat" request dispatched from an asset tab card.
   * ChatPage resolves the asset and prefills the chat input with the
   * relevant text (slash command, prompt content, etc.).
   */
  pendingUse?: AssetUseRequest | null;
  /** Cleared once the pending-use has been consumed. */
  onPendingUseConsumed?: () => void;
  /**
   * User clicked "New chat".  Parent App.tsx clears localStorage and bumps
   * chatKey to remount this whole tree.
   */
  onNewChat?: () => void;
}

export function ChatPage({
  onQuickReply,
  pendingPrompt,
  onPendingPromptConsumed,
  pendingUse,
  onPendingUseConsumed,
  onNewChat,
}: ChatPageProps) {
  const session = useChatSession();
  const { state: healthState, ready } = useHealth();
  const { agents, loading: agentsLoading, error: agentsError } = useAgents();
  const prompts = usePrompts();
  const commands = useCommands();
  const skills = useSkills();
  const mcps = useMcpConfigs();
  const agentName = pickAgentName(ready);
  const active = useActiveAssets(session.sessionId);

  // If the stored agent code isn't in the list (e.g. deleted), drop it.
  useEffect(() => {
    if (!active.agentCode) return;
    if (agentsLoading) return;
    if (agents.length === 0) return;
    if (!agents.some((a) => a.code === active.agentCode)) {
      active.setAgentCode(null);
    }
  }, [agents, agentsLoading, active]);

  // Per-turn extras for the chat body — derived from the active asset sets.
  const extraMcpServers = useMemo(() => {
    const out: Record<string, Record<string, unknown>> = {};
    for (const code of active.activeMcps) {
      const m = mcps.mcps.find((x) => x.code === code);
      if (m) out[code] = m as unknown as Record<string, unknown>;
    }
    return out;
  }, [active.activeMcps, mcps.mcps]);

  const extraSystemMessages = useMemo(() => {
    const out: string[] = [];
    for (const code of active.activePrompts) {
      const p = prompts.prompts.find((x) => x.code === code);
      if (p?.content) out.push(p.content);
    }
    for (const code of active.activeSkills) {
      const s = skills.skills.find((x) => x.code === code);
      if (s?.prompt_template) out.push(s.prompt_template);
    }
    return out;
  }, [active.activePrompts, active.activeSkills, prompts.prompts, skills.skills]);

  const chat = useChatStream({
    sessionId: session.sessionId ?? undefined,
    onSessionChange: (id) => session.setSessionId(id),
    onSessionExpired: () => session.setSessionId(null),
    agentName,
    agentCode: active.agentCode ?? undefined,
    extraMcpServers,
    extraSystemMessages,
  });

  // Pull existing history once when we know the session id.
  const [historyLoaded, setHistoryLoaded] = useState(false);
  useEffect(() => {
    if (!session.sessionId) {
      setHistoryLoaded(false);
      chat.reset();
      return;
    }
    if (historyLoaded) return;
    let cancelled = false;
    session
      .loadHistory(session.sessionId)
      .then(() => {
        if (cancelled) return;
        setHistoryLoaded(true);
      })
      .catch(() => setHistoryLoaded(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.sessionId]);

  const isBusy = chat.status === 'sending' || chat.status === 'streaming';

  // Inject prompt from outside.
  useEffect(() => {
    if (!pendingPrompt) return;
    if (isBusy) return;
    chat.send(pendingPrompt);
    onPendingPromptConsumed?.();
    onQuickReply?.(pendingPrompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, isBusy]);

  // Resolve a "use this asset in chat" request from an asset tab.
  // Fetches the asset, derives an appropriate prefill text, and stages
  // it for the next ChatInput mount.
  const [pendingPrefill, setPendingPrefill] = useState<string | null>(null);
  useEffect(() => {
    if (!pendingUse) return;
    let cancelled = false;
    const fetchAndPrefill = async () => {
      try {
        let prefill = '';
        if (pendingUse.type === 'prompt') {
          const p = await promptsApi.get(pendingUse.code);
          prefill = p.content;
        } else if (pendingUse.type === 'command') {
          const c = await commandsApi.get(pendingUse.code);
          prefill = c.slash_command;
        } else if (pendingUse.type === 'skill') {
          const s = await skillsApi.get(pendingUse.code);
          prefill = s.prompt_template ?? `[skill ${s.code}]`;
        } else if (pendingUse.type === 'mcp') {
          const m = await mcpConfigsApi.get(pendingUse.code);
          prefill = `[mcp ${m.code} (${m.mcp_type})] ${m.url ?? m.command ?? ''}`.trim();
        }
        if (cancelled) return;
        setPendingPrefill(prefill);
      } catch {
        // ignore — placeholder prefill stays empty; the user can still type
      } finally {
        if (!cancelled) onPendingUseConsumed?.();
      }
    };
    void fetchAndPrefill();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingUse]);

  const handleAgentChange = useCallback(
    (code: string | null) => {
      active.setAgentCode(code);
    },
    [active],
  );

  const handleAssetInvoked = useCallback(
    (req: AssetInvokeRequest) => {
      // Always emit so any other subscriber (analytics, side panels) hears it.
      emit(ASSET_INVOKE_EVENT, req);
      // The store auto-appends via its own listener; we still call the
      // local setters to keep the chip strip in sync when ChatInput is
      // mounted in isolation (e.g. before the store listener is wired).
      switch (req.type) {
        case 'agent':
          active.setAgentCode(req.code);
          break;
        case 'mcp':
          active.addMcp(req.code);
          break;
        case 'prompt':
          active.addPrompt(req.code);
          break;
        case 'skill':
          active.addSkill(req.code);
          break;
        case 'command':
          // /commands go through COMMAND_EXECUTED_EVENT (handled below).
          break;
      }
    },
    [active],
  );

  const handleCommandExecuted = useCallback(
    (code: string, slash: string, summary: string) => {
      const evt: CommandExecutedEvent = {
        code,
        slash_command: slash,
        summary,
        at: new Date().toISOString(),
      };
      emit(COMMAND_EXECUTED_EVENT, evt);
    },
    [],
  );

  const handleSend = useCallback(
    (content: string) => {
      chat.send(content);
      // One-turn prompts/skills have been sent — clear them so they don't
      // stick around for the next turn.
      active.consumeOneTurn();
    },
    [chat, active],
  );

  const handleQuickReply = useCallback(
    (value: string) => {
      chat.send(value);
      active.consumeOneTurn();
    },
    [chat, active],
  );

  const handleAbort = useCallback(() => {
    chat.abort();
  }, [chat]);

  const handleAccessLevel = useCallback(
    (level: AccessLevel) => {
      active.setAccessLevel(level);
      emit(ACCESS_LEVEL_CHANGED_EVENT, { level, at: new Date().toISOString() });
    },
    [active],
  );

  const handleCraft = useCallback(() => {
    emit(CRAFT_AGENT_REQUESTED_EVENT, { at: new Date().toISOString() });
    logger.info('Craft agent from this conversation — coming soon');
  }, []);

  const handleClearExecuted = useCallback(
    (code: string) => {
      // No store-side clear in the current spec; local-only UI affordance.
      // We mutate the local cache by re-emitting with a sentinel so the
      // store filters out by code on the next emit.  For now the chip is
      // read-only — this is wired so future store support drops in cleanly.
      void code;
    },
    [],
  );

  return (
    <div className="chat-page">
      <HealthBanner
        state={healthState}
        sessionLabel={labelFor(session.info)}
      />
      {onNewChat && (
        <ChatToolbar
          onNewChat={onNewChat}
          agents={agents}
          agentsLoading={agentsLoading}
          agentsError={agentsError}
          selectedAgentCode={active.agentCode}
          onAgentChange={handleAgentChange}
        />
      )}
      <ChatShell
        agentCode={active.agentCode}
        agents={agents}
        setAgentCode={active.setAgentCode}
        activeMcps={active.activeMcps}
        addMcp={active.addMcp}
        removeMcp={active.removeMcp}
        activePrompts={active.activePrompts}
        activeSkills={active.activeSkills}
        executedCommands={active.executedCommands}
        accessLevel={active.accessLevel}
        setAccessLevel={handleAccessLevel}
        prompts={prompts.prompts}
        commands={commands.commands}
        skills={skills.skills}
        mcps={mcps.mcps}
        onCraft={handleCraft}
        onClearExecuted={handleClearExecuted}
      />
      {chat.messages.length === 0 ? (
        <div className="chat-page-empty">
          <WelcomeMessage
            onQuickReply={handleQuickReply}
            backendReady={healthState === 'healthy'}
          />
        </div>
      ) : (
        <MessageList loading={isBusy}>
          {chat.messages.map((msg: ChatMessage) => (
            <ChatBubble
              key={msg.id}
              message={msg}
              onQuickReply={handleQuickReply}
              onAbort={handleAbort}
            />
          ))}
        </MessageList>
      )}
      {chat.error && chat.messages.length > 0 && (
        <div className="chat-page-error" role="alert">
          <span>{chat.error}</span>
          <button
            type="button"
            className="chat-page-error-dismiss"
            onClick={() => chat.reset()}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}
      <ChatInput
        onSend={handleSend}
        disabled={isBusy}
        placeholder={
          isBusy
            ? 'Generating...'
            : pendingPrefill
              ? 'Asset loaded — edit and press Enter to send'
              : 'Message AI...'
        }
        initialValue={pendingPrefill ?? ''}
        prompts={prompts.prompts}
        commands={commands.commands}
        skills={skills.skills}
        mcps={mcps.mcps}
        onAssetInvoked={handleAssetInvoked}
        onCommandExecuted={handleCommandExecuted}
      />
    </div>
  );
}

// --- ChatShell ---------------------------------------------------------------

interface ChatShellProps {
  agentCode: string | null;
  agents: AgentAsset[];
  setAgentCode: (code: string | null) => void;
  activeMcps: string[];
  addMcp: (code: string) => void;
  removeMcp: (code: string) => void;
  activePrompts: string[];
  activeSkills: string[];
  executedCommands: CommandExecutedEvent[];
  accessLevel: AccessLevel;
  setAccessLevel: (level: AccessLevel) => void;
  prompts: PromptAsset[];
  commands: CommandAsset[];
  skills: SkillAsset[];
  mcps: McpConfigAsset[];
  onCraft: () => void;
  onClearExecuted: (code: string) => void;
}

function ChatShell(props: ChatShellProps) {
  const {
    agentCode,
    agents,
    setAgentCode,
    activeMcps,
    removeMcp,
    activePrompts,
    activeSkills,
    executedCommands,
    accessLevel,
    setAccessLevel,
    prompts,
    skills,
    mcps,
    onCraft,
    onClearExecuted,
  } = props;

  const agent = agentCode ? agents.find((a) => a.code === agentCode) : null;
  const mcpById = new Map(mcps.map((m) => [m.code, m]));
  const promptById = new Map(prompts.map((p) => [p.code, p]));
  const skillById = new Map(skills.map((s) => [s.code, s]));

  const totalChips =
    (agentCode ? 1 : 0) +
    activeMcps.length +
    activePrompts.length +
    activeSkills.length +
    executedCommands.length;

  return (
    <div className="chat-shell">
      <div className="chat-shell-chips">
        {agentCode && (
          <Chip
            kind="agent"
            label={agent ? `${agent.name}` : agentCode}
            onRemove={() => setAgentCode(null)}
          />
        )}
        {activeMcps.map((code) => (
          <Chip
            key={`mcp:${code}`}
            kind="mcp"
            label={mcpById.get(code)?.name ?? code}
            onRemove={() => removeMcp(code)}
          />
        ))}
        {activePrompts.map((code) => (
          <Chip
            key={`prompt:${code}`}
            kind="prompt"
            label={promptById.get(code)?.name ?? code}
            onRemove={() => undefined}
            oneShot
          />
        ))}
        {activeSkills.map((code) => (
          <Chip
            key={`skill:${code}`}
            kind="skill"
            label={skillById.get(code)?.name ?? code}
            onRemove={() => undefined}
            oneShot
          />
        ))}
        {executedCommands.map((c) => (
          <span
            key={`executed:${c.code}`}
            className="chat-shell-executed"
            title={`${c.slash_command} — ${c.summary}`}
          >
            已执行 {c.slash_command}
            <button
              type="button"
              className="chat-shell-chip-remove"
              onClick={() => onClearExecuted(c.code)}
              aria-label={`Clear executed ${c.slash_command}`}
            >
              ×
            </button>
          </span>
        ))}
        {totalChips === 0 && (
          <span className="chat-shell-trigger-hint">
            Type @ to attach an asset · / to run a command
          </span>
        )}
      </div>
      <div className="chat-shell-permission">
        <PermissionPill level={accessLevel} onChange={setAccessLevel} />
        <button
          type="button"
          className="chat-shell-chip-remove"
          onClick={onCraft}
          aria-label="Craft agent from this conversation"
          title="Craft agent from this conversation"
          style={{ marginRight: 0, width: 'auto', padding: '0 6px' }}
        >
          ✦ Craft
        </button>
      </div>
    </div>
  );
}

interface ChipProps {
  kind: 'agent' | 'mcp' | 'prompt' | 'skill' | 'command';
  label: string;
  onRemove: () => void;
  oneShot?: boolean;
}

function Chip({ kind, label, onRemove, oneShot }: ChipProps) {
  return (
    <span className="chat-shell-chip" title={label}>
      <span className="chat-shell-chip-icon" data-icon={kind} aria-hidden="true" />
      <span className="chat-shell-chip-label">{label}</span>
      {oneShot && <span className="chat-shell-chip-icon" title="One-shot (cleared on send)">1×</span>}
      <button
        type="button"
        className="chat-shell-chip-remove"
        onClick={onRemove}
        aria-label={`Remove ${label}`}
      >
        ×
      </button>
    </span>
  );
}

interface PermissionPillProps {
  level: AccessLevel;
  onChange: (level: AccessLevel) => void;
}

function PermissionPill({ level, onChange }: PermissionPillProps) {
  const options: Array<{ value: AccessLevel; label: string; title: string }> = [
    { value: 'restricted', label: '受限', title: '无工具权限' },
    { value: 'standard', label: '标准', title: '只读 + 网络搜索' },
    { value: 'full', label: '完全访问权限', title: '允许所有工具 (workbuddy 模式)' },
  ];
  return (
    <div
      className={`chat-shell-permission-toggle chat-shell-permission--${level}`}
      role="radiogroup"
      aria-label="Tool permission level"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={level === o.value}
          className={level === o.value ? 'is-active' : ''}
          onClick={() => onChange(o.value)}
          title={o.title}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- Existing helpers (unchanged) -------------------------------------------

function pickAgentName(ready: ReturnType<typeof useHealth>['ready']): string | undefined {
  if (!ready?.agents) return undefined;
  if (Array.isArray(ready.agents)) {
    return ready.agents.find((n): n is string => typeof n === 'string' && n.length > 0);
  }
  const names = Object.keys(ready.agents);
  return names.find((n) => n && typeof n === 'string');
}

function labelFor(info: { agent_name?: string; session_id?: string } | null): string {
  if (!info) return 'No session';
  const shortId = (info.session_id ?? '').slice(0, 8);
  return `${info.agent_name ?? 'agent'} · ${shortId || '...'}`;
}

function HealthBanner({
  state,
  sessionLabel,
}: {
  state: ReturnType<typeof useHealth>['state'];
  sessionLabel: string;
}) {
  let text = '';
  switch (state) {
    case 'healthy':
      text = `Connected · ${sessionLabel}`;
      break;
    case 'degraded':
      text = 'Backend is degraded — some features may be unavailable';
      break;
    case 'unreachable':
      text = 'Cannot reach backend — check the server';
      break;
    case 'unknown':
    default:
      text = 'Connecting to backend...';
  }
  return (
    <div className={`chat-health-banner chat-health-${state}`}>
      <span className="chat-health-dot" />
      <span className="chat-health-text">{text}</span>
    </div>
  );
}

function ChatToolbar({
  onNewChat,
  agents,
  agentsLoading,
  agentsError,
  selectedAgentCode,
  onAgentChange,
}: {
  onNewChat: () => void;
  agents: Array<{ code: string; name: string; description?: string | null }>;
  agentsLoading: boolean;
  agentsError: string | null;
  selectedAgentCode: string | null;
  onAgentChange: (code: string | null) => void;
}) {
  return (
    <div className="chat-toolbar">
      <div className="chat-toolbar-title">Chat</div>
      <label className="chat-toolbar-agent" title="Select which agent profile to inject into the chat">
        <span className="chat-toolbar-agent-label">Agent</span>
        <select
          className="chat-toolbar-agent-select"
          value={selectedAgentCode ?? ''}
          onChange={(e) => onAgentChange(e.target.value || null)}
          disabled={agentsLoading}
        >
          <option value="">(none — use scenario defaults)</option>
          {agents.map((a) => (
            <option key={a.code} value={a.code}>
              {a.name} ({a.code})
            </option>
          ))}
        </select>
        {agentsError && (
          <span className="chat-toolbar-agent-error" title={agentsError}>
            ⚠
          </span>
        )}
      </label>
      <button
        type="button"
        className="chat-toolbar-new-btn"
        onClick={onNewChat}
        title="Clear the current conversation and start a new session"
      >
        <PlusIcon />
        <span>New chat</span>
      </button>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}